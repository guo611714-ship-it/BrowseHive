"""任务计划管理器 — Magentic模式：计划/追踪/卡死检测/自动重规划"""

import json
import time
import logging
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Awaitable
from pathlib import Path
from .task_state import TaskStateManager, TaskState

logger = logging.getLogger(__name__)


@dataclass
class TaskPlan:
    """一个完整的任务计划"""
    id: str
    goal: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "planning"  # planning | executing | stalled | completed | failed
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    stall_count: int = 0
    max_stalls: int = 3
    plan_version: int = 1


@dataclass
class ProgressLedger:
    """进度账本 — 追踪每轮执行结果"""
    is_request_satisfied: bool = False
    is_in_loop: bool = False
    is_progress_being_made: bool = True
    next_step: Optional[str] = None
    last_output: str = ""
    rounds_since_progress: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)


class TaskPlanManager:
    """任务计划管理器 — 支持计划/执行/卡死检测/自动重规划"""

    def __init__(self, state_manager: TaskStateManager,
                 plan_path: str = ".team/task_plans.json",
                 replan_fn: Optional[Callable] = None):
        """
        Args:
            state_manager: 任务状态管理器
            plan_path: 计划持久化路径
            replan_fn: 异步重规划函数 (goal, failed_steps, context) -> new_steps
        """
        self.state_manager = state_manager
        self.plan_path = Path(plan_path)
        self.plans: Dict[str, TaskPlan] = {}
        self.ledger = ProgressLedger()
        self._replan_fn = replan_fn
        self._load()

    def _load(self):
        if self.plan_path.exists():
            try:
                data = json.loads(self.plan_path.read_text(encoding="utf-8"))
                for p in data.get("plans", []):
                    self.plans[p["id"]] = TaskPlan(**p)
            except Exception as e:
                logger.debug("caught exception: %s", e)

    def _save(self):
        self.plan_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"plans": [asdict(p) for p in self.plans.values()]}
        self.plan_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def create_plan(self, goal: str, steps: List[Dict[str, Any]]) -> TaskPlan:
        """创建任务计划

        Args:
            goal: 目标描述
            steps: [{"task_id": str, "agent_type": str, "task": str,
                      "depends_on": [str]}]
        """
        plan_id = f"plan_{int(time.time())}"
        plan = TaskPlan(id=plan_id, goal=goal, steps=steps, status="planning")

        for step in steps:
            self.state_manager.add_task(
                task_id=step["task_id"],
                name=step["task"],
                agent_type=step.get("agent_type"),
                depends_on=step.get("depends_on", [])
            )
            step["status"] = "pending"

        self.plans[plan_id] = plan
        self._save()
        logger.info(f"计划创建: {plan_id}, {len(steps)} 个步骤, 目标: {goal[:50]}")
        return plan

    def get_executable_steps(self, plan_id: str) -> List[Dict[str, Any]]:
        """获取当前可执行的步骤（依赖已完成）"""
        plan = self.plans.get(plan_id)
        if not plan:
            return []

        done_tasks = {
            t.id for t in self.state_manager.tasks.values()
            if t.status in ("done", "completed")
        }

        executable = []
        for step in plan.steps:
            if step["status"] != "pending":
                continue
            deps = set(step.get("depends_on", []))
            if deps.issubset(done_tasks):
                executable.append(step)
        return executable

    def update_step_status(self, plan_id: str, task_id: str,
                           status: str, result: str = None):
        """更新步骤状态"""
        plan = self.plans.get(plan_id)
        if not plan:
            return

        for step in plan.steps:
            if step["task_id"] == task_id:
                step["status"] = status
                break

        self.state_manager.update_status(task_id, status, result)

        self.ledger.history.append({
            "plan_id": plan_id, "task_id": task_id,
            "status": status, "timestamp": datetime.now().isoformat()
        })

        if status == "done":
            self.ledger.rounds_since_progress = 0
            self.ledger.is_progress_being_made = True
        elif status == "failed":
            self.ledger.rounds_since_progress += 1

        # 更新plan状态
        all_done = all(s["status"] in ("done", "failed") for s in plan.steps)
        any_failed = any(s["status"] == "failed" for s in plan.steps)

        if all_done:
            plan.status = "completed" if not any_failed else "failed"
            self.ledger.is_request_satisfied = True
        elif self._detect_stall(plan):
            plan.status = "stalled"
            plan.stall_count += 1
            self.ledger.is_progress_being_made = False
            logger.warning(f"计划 {plan_id} 卡死 (第{plan.stall_count}次)")

        plan.updated_at = datetime.now().isoformat()
        self._save()

    def _detect_stall(self, plan: TaskPlan) -> bool:
        """检测是否卡死"""
        if self.ledger.rounds_since_progress >= 2:
            return True
        if plan.stall_count >= plan.max_stalls:
            return True
        return False

    async def auto_replan(self, plan_id: str, context: str = "") -> Optional[TaskPlan]:
        """自动重规划 — 卡死时用LLM生成新计划

        Args:
            plan_id: 计划ID
            context: 额外上下文（失败原因等）

        Returns:
            重规划后的计划，或None（无法重规划）
        """
        plan = self.plans.get(plan_id)
        if not plan:
            return None

        if not self._replan_fn:
            logger.warning("无重规划函数，跳过auto_replan")
            return None

        if plan.stall_count >= plan.max_stalls:
            logger.warning(f"计划 {plan_id} 已达最大重规划次数 ({plan.max_stalls})")
            return None

        # 收集失败步骤和已完成结果
        failed_steps = [s for s in plan.steps if s["status"] == "failed"]
        completed_results = []
        for s in plan.steps:
            if s["status"] == "done":
                task = self.state_manager.tasks.get(s["task_id"])
                completed_results.append({
                    "task": s["task"],
                    "result": task.result[:500] if task and task.result else ""
                })

        try:
            new_steps = await self._replan_fn(
                goal=plan.goal,
                failed_steps=failed_steps,
                completed_results=completed_results,
                context=context,
                plan_version=plan.plan_version
            )
            if new_steps:
                return self.replan(plan_id, new_steps)
        except Exception as e:
            logger.error(f"自动重规划失败: {e}")

        return None

    def replan(self, plan_id: str, new_steps: List[Dict[str, Any]] = None) -> TaskPlan:
        """重规划 — 生成新版本计划"""
        old_plan = self.plans.get(plan_id)
        if not old_plan:
            raise ValueError(f"计划 {plan_id} 不存在")

        old_plan.plan_version += 1
        old_plan.status = "executing"
        old_plan.stall_count = 0
        self.ledger.rounds_since_progress = 0
        self.ledger.is_progress_being_made = True

        if new_steps:
            completed = [s for s in old_plan.steps if s["status"] == "done"]
            old_plan.steps = completed + new_steps

            for step in new_steps:
                self.state_manager.add_task(
                    task_id=step["task_id"],
                    name=step["task"],
                    agent_type=step.get("agent_type"),
                    depends_on=step.get("depends_on", [])
                )

        old_plan.updated_at = datetime.now().isoformat()
        self._save()
        logger.info(f"计划重规划: {plan_id} v{old_plan.plan_version}")
        return old_plan

    async def execute_plan(self, plan_id: str, dispatcher=None,
                           max_rounds: int = 20) -> Dict[str, Any]:
        """DAG自动调度 — 自动执行就绪步骤"""
        if not dispatcher:
            from ..tools.dispatch_tools import get_dispatcher
            dispatcher = get_dispatcher()

        plan = self.plans.get(plan_id)
        if not plan:
            return {"error": f"计划 {plan_id} 不存在"}

        if not dispatcher:
            return {"error": "Dispatcher未初始化"}

        plan.status = "executing"
        self._save()
        results = []

        for round_num in range(max_rounds):
            ready = self.get_executable_steps(plan_id)
            if not ready:
                all_done = all(s["status"] in ("done", "failed") for s in plan.steps)
                if all_done:
                    plan.status = "completed"
                    self._save()
                    return {"status": "completed", "results": results}
                pending = [s for s in plan.steps if s["status"] == "pending"]
                if pending:
                    plan.status = "stalled"
                    self._save()
                    return {"status": "stalled", "results": results,
                            "pending": [s["task_id"] for s in pending]}
                # 检查是否有卡在running的步骤（可能是dispatch异常导致）
                running = [s for s in plan.steps if s["status"] == "running"]
                if running:
                    for s in running:
                        self.update_step_status(plan_id, s["task_id"], "failed", "[超时] 步骤执行异常")
                        results.append({"task_id": s["task_id"], "status": "failed", "summary": "[超时]"})
                break

            # 并行执行
            tasks_to_dispatch = []
            for step in ready:
                step["status"] = "running"
                tasks_to_dispatch.append({
                    "agent_type": step.get("agent_type", "xiaohuangmen"),
                    "task": step["task"],
                    "expected_output": step.get("expected_output"),
                    "context": f"DAG步骤 {step['task_id']}, 依赖已完成"
                })

            try:
                dispatch_results = await dispatcher.dispatch_parallel(
                    tasks_to_dispatch, max_concurrent=5
                )
            except Exception as e:
                logger.error(f"DAG dispatch异常: {e}")
                for step in ready:
                    self.update_step_status(plan_id, step["task_id"], "failed", f"[异常] {e}")
                    results.append({"task_id": step["task_id"], "status": "failed", "summary": str(e)[:200]})
                continue

            # 收集结果
            for i, result in enumerate(dispatch_results):
                if i < len(ready):
                    step = ready[i]
                    summary = result.get("summary", "") if isinstance(result, dict) else str(result)[:200]
                    # 判断真实状态：基于result["status"]，不是summary子串匹配
                    dispatch_status = result.get("status", "failed") if isinstance(result, dict) else "failed"
                    status = "done" if dispatch_status == "completed" else "failed"
                    self.update_step_status(plan_id, step["task_id"], status, summary)
                    results.append({
                        "task_id": step["task_id"],
                        "status": status,
                        "summary": summary[:200]
                    })

        plan.status = "completed" if all(s["status"] in ("done", "failed") for s in plan.steps) else "failed"
        self._save()
        return {"status": plan.status, "results": results}

    def get_plan_status(self, plan_id: str) -> Dict[str, Any]:
        """获取计划状态摘要"""
        plan = self.plans.get(plan_id)
        if not plan:
            return {"error": f"计划 {plan_id} 不存在"}

        steps_summary = []
        for step in plan.steps:
            task = self.state_manager.tasks.get(step["task_id"])
            steps_summary.append({
                "task_id": step["task_id"],
                "agent_type": step.get("agent_type", "unknown"),
                "task": step["task"][:80],
                "status": step["status"],
                "result": task.result[:200] if task and task.result else None
            })

        return {
            "plan_id": plan.id,
            "goal": plan.goal,
            "status": plan.status,
            "version": plan.plan_version,
            "stall_count": plan.stall_count,
            "steps": steps_summary,
            "progress": self.state_manager.get_progress()
        }

    def _sync_step_statuses(self, plan_id: str):
        """同步plan.steps状态与TaskState"""
        plan = self.plans.get(plan_id)
        if not plan:
            return
        for step in plan.steps:
            task = self.state_manager.tasks.get(step["task_id"])
            if task and step["status"] != task.status:
                step["status"] = task.status

    async def run_dag_scheduler(self, plan_id: str, dispatcher) -> List[Dict[str, Any]]:
        """DAG自动调度器 — 自动执行就绪任务，直到所有任务完成"""
        plan = self.plans.get(plan_id)
        if not plan:
            return []

        plan.status = "executing"
        results = []

        while True:
            # 找出所有就绪任务
            ready = self.get_executable_steps(plan_id)
            if not ready:
                # 检查是否全部完成
                all_done = all(s["status"] in ("done", "failed") for s in plan.steps)
                if all_done:
                    plan.status = "completed" if not any(s["status"] == "failed" for s in plan.steps) else "failed"
                break

            # 并行执行所有就绪任务
            async def _exec_step(step):
                task_id = step["task_id"]
                agent_type = step.get("agent_type", "xiaohuangmen")
                task_desc = step["task"]

                # 更新状态为running
                self.update_step_status(plan_id, task_id, "running")

                # 收集依赖结果作为上下文
                dep_results = []
                for dep_id in step.get("depends_on", []):
                    dep_task = self.state_manager.tasks.get(dep_id)
                    if dep_task and dep_task.result:
                        dep_results.append(f"[{dep_id}] {dep_task.result[:200]}")
                dep_context = "\n".join(dep_results) if dep_results else None

                # 执行
                try:
                    result = await dispatcher.dispatch(
                        agent_type=agent_type, task=task_desc, context=dep_context
                    )
                    status = result.get("status", "failed")
                    summary = result.get("summary", "")
                    self.update_step_status(plan_id, task_id, status, summary)
                    return {"task_id": task_id, "status": status, "summary": summary[:200]}
                except Exception as e:
                    self.update_step_status(plan_id, task_id, "failed", str(e))
                    return {"task_id": task_id, "status": "failed", "summary": str(e)[:200]}

            # 并行执行
            step_results = await asyncio.gather(
                *[_exec_step(step) for step in ready],
                return_exceptions=True
            )

            for r in step_results:
                if isinstance(r, Exception):
                    results.append({"status": "failed", "summary": str(r)[:200]})
                else:
                    results.append(r)

            # 同步plan.steps状态
            self._sync_step_statuses(plan_id)

            # 检测卡死
            if not any(r.get("status") in ("done", "completed") for r in step_results if isinstance(r, dict)):
                self.ledger.rounds_since_progress += 1
                if self.ledger.rounds_since_progress >= 3:
                    logger.warning(f"DAG调度卡死: plan={plan_id}")
                    plan.status = "stalled"
                    break
            else:
                self.ledger.rounds_since_progress = 0

        self._save()
        return results

    def to_dict(self) -> Dict:
        return {
            "plans": [asdict(p) for p in self.plans.values()],
            "ledger": asdict(self.ledger)
        }
