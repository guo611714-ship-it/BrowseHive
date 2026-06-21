"""DAG 任务编排引擎 — 支持依赖管理与拓扑排序执行"""

import json
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
from collections import defaultdict, deque


@dataclass
class TaskNode:
    """DAG 中的任务节点"""
    id: str
    name: str
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, running, done, failed, skipped
    result: Optional[str] = None


class DAGExecutor:
    """DAG 任务执行器

    用法:
        dag = DAGExecutor()
        dag.add_task(TaskNode(id="a", name="读取文件"))
        dag.add_task(TaskNode(id="b", name="分析代码", dependencies=["a"]))
        dag.add_task(TaskNode(id="c", name="生成报告", dependencies=["a", "b"]))

        async def execute(task):
            # 根据 task.name 执行具体操作
            return f"{task.name} 完成"

        results = await dag.run_dag(execute)
    """

    def __init__(self):
        self.tasks: Dict[str, TaskNode] = {}
        self._adj: Dict[str, List[str]] = defaultdict(list)  # from -> [to]

    def add_task(self, node: TaskNode) -> None:
        """添加任务节点"""
        self.tasks[node.id] = node
        for dep_id in node.dependencies:
            self._adj[dep_id].append(node.id)

    def add_dependency(self, from_id: str, to_id: str) -> None:
        """添加依赖关系：to_id 依赖 from_id"""
        if to_id in self.tasks:
            self.tasks[to_id].dependencies.append(from_id)
            self._adj[from_id].append(to_id)

    def _topological_sort(self) -> List[List[str]]:
        """拓扑排序，返回分层执行计划（同层可并行）"""
        in_degree = defaultdict(int)
        for nid in self.tasks:
            in_degree[nid] = len(self.tasks[nid].dependencies)

        layers = []
        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])

        while queue:
            layer = list(queue)
            layers.append(layer)
            next_queue = deque()
            for nid in layer:
                for child in self._adj[nid]:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        next_queue.append(child)
            queue = next_queue

        # 检测循环
        executed = sum(len(l) for l in layers)
        if executed != len(self.tasks):
            raise ValueError(f"DAG 存在循环依赖 ({executed}/{len(self.tasks)} 任务可执行)")

        return layers

    async def run_dag(self, execute_fn: Callable[[TaskNode], Any]) -> Dict[str, Any]:
        """执行 DAG 任务

        Args:
            execute_fn: 异步执行函数，接受 TaskNode，返回结果

        Returns:
            {"results": {task_id: result}, "summary": {...}}
        """
        # 重置状态
        for node in self.tasks.values():
            node.status = "pending"
            node.result = None

        layers = self._topological_sort()
        results = {}
        failed_ids = set()

        for layer in layers:
            # 跳过依赖已失败的任务
            runnable = []
            for nid in layer:
                deps_ok = all(d not in failed_ids for d in self.tasks[nid].dependencies)
                if deps_ok:
                    runnable.append(nid)
                else:
                    self.tasks[nid].status = "skipped"
                    self.tasks[nid].result = "依赖任务失败"

            # 并行执行同层任务
            async def _run_one(task_id):
                node = self.tasks[task_id]
                node.status = "running"
                try:
                    raw = execute_fn(node)
                    # 支持同步和异步执行函数
                    if asyncio.iscoroutine(raw):
                        result = await raw
                    else:
                        result = raw
                    node.status = "done"
                    node.result = str(result) if result else None
                    results[task_id] = result
                except Exception as e:
                    node.status = "failed"
                    node.result = str(e)
                    failed_ids.add(task_id)
                    results[task_id] = None

            if runnable:
                await asyncio.gather(*[_run_one(nid) for nid in runnable])

        total = len(self.tasks)
        done = sum(1 for t in self.tasks.values() if t.status == "done")
        failed = sum(1 for t in self.tasks.values() if t.status == "failed")
        skipped = sum(1 for t in self.tasks.values() if t.status == "skipped")

        return {
            "results": results,
            "summary": {
                "total": total,
                "done": done,
                "failed": failed,
                "skipped": skipped,
                "success_rate": f"{done}/{total}",
            },
        }

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "tasks": {nid: asdict(node) for nid, node in self.tasks.items()},
            "adjacency": dict(self._adj),
        }

    def save(self, path: str):
        """保存到文件"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str) -> "DAGExecutor":
        """从文件加载"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        dag = cls()
        for nid, node_data in data.get("tasks", {}).items():
            dag.add_task(TaskNode(**node_data))
        return dag
