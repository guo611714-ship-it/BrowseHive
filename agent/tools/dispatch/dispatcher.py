"""SubagentDispatcher 类 — 核心调度逻辑

已拆分模块：
  context.py   — _build_shared_context / _filter_relevance (ContextMixin)
  review.py    — _auto_verify (ReviewMixin)
  refine.py    — dispatch_iterative_refine_impl (独立函数)
"""

import json
import re
import time
import uuid as _uuid
from datetime import datetime
from typing import Dict, Any, List, Callable, Optional
from pathlib import Path
import asyncio
import logging

from ...subagents.registry import SubagentRegistry, SubagentSpec
from ...config import AGENT_MEMORY_DIR
from ..tool_registry import get_tool_schemas
from ..git_tools import create_backup_branch, git_diff_summary
from .approval import _pending_approvals, _shared_context
from .context import ContextMixin
from .review import ReviewMixin

logger = logging.getLogger(__name__)


class SubagentDispatcher(ContextMixin, ReviewMixin):
    """子代理调度器 — 多轮工具调用版（支持上下文注入）"""

    def __init__(self, model_orchestrator=None, team_store=None, tools=None,
                 memory=None, progress_callback=None, skill_router=None):
        from .parallel_core import claude_code_printer
        self.registry = SubagentRegistry
        self.model_orchestrator = model_orchestrator
        self.team_store = team_store
        self.tools = tools or {}
        self.memory = memory
        self.progress = progress_callback or claude_code_printer
        self.skill_router = skill_router

    def _resolve_client(self, agent_type: str):
        """选择 LLM client（模型编排器优先，回退全局）"""
        from .parallel_core import _global_llm_client
        if self.model_orchestrator and self.team_store:
            teammates = self.team_store.teammates if hasattr(self.team_store, 'teammates') else []
            for t in teammates:
                if t.get("agent_type") == agent_type or t.get("name") == agent_type:
                    return self.model_orchestrator.get_client_for_agent(t.get("name"), t)
        return _global_llm_client

    def _build_subagent_tools(self, spec: SubagentSpec) -> Dict[str, Callable]:
        """根据 spec 过滤出子代理可用的工具 + 自动注入浏览器AI"""
        allowed = set(spec.allowed_tools)
        filtered = {name: fn for name, fn in self.tools.items() if name in allowed}
        # P0: 自动注入浏览器AI工具（当agent有smart_ask权限时）
        if "smart_ask" in allowed:
            for tool_name in ["ask_doubao", "ask_deepseek_browser", "ask_bing", "ask_ouyi"]:
                if tool_name in self.tools and tool_name not in filtered:
                    filtered[tool_name] = self.tools[tool_name]
        # 典簿/内官监测试工具注入
        from ..test_tools import TEST_TOOL_FUNCTIONS
        for name, func in TEST_TOOL_FUNCTIONS.items():
            if name in allowed and name not in filtered:
                filtered[name] = func
        return filtered

    # ── _build_shared_context / _filter_relevance 来自 ContextMixin ──
    # ── _auto_verify 来自 ReviewMixin ──────────────────────────────

    async def dispatch(self, agent_type: str, task: str,
                       expected_output: str = None,
                       evidence_required: bool = True,
                       context: str = None,
                       timeout: float = 300.0) -> Dict[str, Any]:
        """派遣子代理执行任务（多轮工具调用，带全局超时）"""
        from .parallel_core import _failure_result
        try:
            return await asyncio.wait_for(
                self._dispatch_impl(agent_type, task, expected_output,
                                    evidence_required, context),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"dispatch超时 ({timeout}s): {agent_type} - {task[:50]}")
            return _failure_result(agent_type, agent_type, task,
                                   f"[超时] 任务执行超过{timeout}秒")

    async def _dispatch_impl(self, agent_type: str, task: str,
                             expected_output: str = None,
                             evidence_required: bool = True,
                             context: str = None) -> Dict[str, Any]:
        """派遣子代理执行任务（内部实现）"""
        from .parallel_core import (
            AgentProgressEvent, _failure_result, _build_tool_schema,
            _safe_str, _is_simple_task, _validate_result,
        )
        spec = self.registry.get_spec(agent_type)
        if not spec:
            return _failure_result(agent_type, "", task,
                                   f"[错误] 未知的子代理类型: {agent_type}")

        # P0: 模型选择（优先级：spec.preferred_model > 复杂度路由 > 默认）
        orchestrator = self.model_orchestrator
        complexity = 0
        if orchestrator:
            # 优先使用子代理指定的模型
            if spec.preferred_model:
                client = orchestrator._get_or_create_client(spec.preferred_model)
                if client:
                    logger.info(f"子代理 {agent_type} 使用指定模型: {client.model}")
                else:
                    # 指定模型不存在，fallback到复杂度路由
                    complexity = orchestrator.score_complexity(task)
                    client = orchestrator.get_model_for_complexity(complexity)
            else:
                complexity = orchestrator.score_complexity(task)
                client = orchestrator.get_model_for_complexity(complexity)
                logger.info(f"任务复杂度: {complexity}/5, 模型: {client.model if client else 'none'}")
        else:
            client = self._resolve_client(agent_type)

        if not client:
            return _failure_result(agent_type, spec.display_name, task,
                                   "[错误] LLM 客户端未配置，无法派遣子代理。")

        # P0: 非只读子代理自动创建备份分支
        backup_info = None
        if not spec.read_only:
            try:
                backup_info = create_backup_branch(label=agent_type)
            except Exception as e:
                logger.debug("caught exception: %s", e)
                backup_info = None

        # P0: 检查点创建（崩溃后可断点续跑）
        from ...tools.checkpoint import CheckpointManager
        _ckpt_mgr = CheckpointManager()
        checkpoint_id = f"{agent_type}_{_uuid.uuid4().hex[:8]}"
        checkpoint = None
        try:
            from ...tools.checkpoint import BrowserCheckpoint
            checkpoint = BrowserCheckpoint(session_id=checkpoint_id, task=task)
            _ckpt_mgr.save(checkpoint)
        except Exception as e:
            logger.debug("caught exception: %s", e)
            checkpoint = None

        # 构造受限工具集
        sub_tools = self._build_subagent_tools(spec)
        tools_schema = _build_tool_schema(spec)

        # 构造系统提示（注入共享上下文 + 工具使用规则）
        shared_context = await self._build_shared_context(task, context, agent_type=agent_type)
        system_prompt = f"你是 {spec.display_name}。\n\n【身份】\n{spec.description}\n"
        if sub_tools:
            system_prompt += f"\n【可用工具】{', '.join(sub_tools.keys())}\n"
        system_prompt += f"\n【任务】\n{task}\n"
        if expected_output:
            system_prompt += f"\n【期望输出】{expected_output}\n"
        if evidence_required:
            system_prompt += "\n请在回复中包含关键证据或文件路径。\n"
        # 工具使用规则
        system_prompt += "\n【工具使用规则】每轮可调用多个独立工具（如同时读取多个文件），但依赖前序结果的工具必须分轮执行。\n"
        # --- Skill 预路由注入 ---
        if self.skill_router:
            skill_info = self.skill_router.route(task)
            if skill_info:
                skill_block = f"""
## 参考 Skill: {skill_info['name']}
{skill_info['description']}

以下是该 skill 的详细指令，请遵循执行：
---
{skill_info['content']}
---
"""
                system_prompt += "\n\n" + skill_block
        # P0: 浏览器AI规则（仅指定子代理可调用）
        if agent_type in ("dongchang_tanshi", "sili_suitang", "neiguan_yingzao", "shangbao_dianbu"):
            system_prompt += """
【浏览器AI工具调用规则（仅中文场景可用）】
你仅可在满足以下任一条件时调用smart_ask等浏览器AI工具，其他场景禁止调用：
1. 任务明确为中文语义处理类（中文文档整理、中文文案润色、中文报告撰写等）
2. NVIDIA原生模型返回的中文内容存在翻译腔、逻辑不通、专业术语错误
3. 需要查询国内特定领域知识（国内云厂商、国内合规要求、中文互联网专属信息）
4. 用户明确要求调用浏览器AI

调用要求：优先选择匹配场景的平台，调用时把完整中文上下文带全，单次任务调用不超过2次，失败后fallback到NVIDIA模型。
"""
        if shared_context:
            system_prompt += f"\n{shared_context}\n"

        # 多轮工具调用循环
        messages = [{"role": "user", "content": task}]
        max_turns = min(spec.max_turns, 50)  # 免费API，放开轮数限制到50
        final_reply = ""
        completed = False
        tools_used = []
        tool_calls_log = []
        files_modified = []
        turn = -1
        progress_pct = 0

        # P1: 开始执行进度
        self.progress(AgentProgressEvent(
            timestamp=datetime.now(), agent_name=spec.display_name,
            step="start", status="running",
            message=f"开始执行: {task[:60]}", progress=0
        ))

        for turn in range(max_turns):
            # P1: LLM调用重试（指数退避）
            response = None
            for retry in range(3):
                try:
                    response = await client.chat(
                        messages=messages,
                        system=system_prompt.strip(),
                        tools=tools_schema if tools_schema else None
                    )
                    # 检查是否为网络错误（需要重试）
                    if response.get("status_code", 200) == -1 and retry < 2:
                        await asyncio.sleep(2 ** (retry + 1))
                        continue
                    break
                except Exception as e:
                    if retry < 2:
                        await asyncio.sleep(2 ** (retry + 1))
                        continue
                    final_reply = f"LLM调用失败: {e}"
                    completed = False
                    # P0: 记录模型失败健康度
                    if orchestrator and client:
                        try:
                            orchestrator.record_model_result(client.model, False)
                        except Exception as e:
                            logger.debug("caught exception: %s", e)
                    break

            if final_reply:
                break

            content = response.get("content", "") or ""
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                final_reply = content
                completed = True
                break

            # 记录 assistant 消息
            assistant_msg = {"role": "assistant", "content": content}
            assistant_msg["tool_calls"] = [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"],
                              "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                for tc in tool_calls
            ]
            messages.append(assistant_msg)

            # 执行工具调用
            for tc in tool_calls:
                tool_name = tc["name"]
                tool_args = tc["arguments"]

                # 记录工具调用（安全序列化参数）
                tool_calls_log.append({
                    "turn": turn, "tool": tool_name,
                    "args": {k: _safe_str(v, 100) for k, v in tool_args.items()}
                })

                # P1: 工具调用进度
                progress_pct = min(progress_pct + 15, 85)
                self.progress(AgentProgressEvent(
                    timestamp=datetime.now(), agent_name=spec.display_name,
                    step="tool_call", status="running",
                    message=f"调用 {tool_name}({_safe_str(tool_args, 50)})",
                    progress=progress_pct
                ))

                # P0: 检查点记录每一步
                if checkpoint:
                    try:
                        _ckpt_mgr.record_step(checkpoint, tool_name, tool_args, {"code": 200})
                        _ckpt_mgr.save(checkpoint)
                    except Exception as e:
                        logger.debug("caught exception: %s", e)

                # 权限验证（标准权限 + 内部工具权限）
                if not self.registry.validate_tool_access(agent_type, tool_name):
                    result_str = f"[权限拒绝] {spec.display_name} 无权使用 {tool_name}"
                elif not self.registry.check_internal_access(agent_type, tool_name):
                    result_str = f"[权限拒绝] {tool_name} 是内部工具，仅允许 {self.registry.is_internal_tool(tool_name)} 使用"
                    logger.warning(f"内部工具越权: {agent_type} 尝试使用 {tool_name}")
                elif tool_name in sub_tools:
                    try:
                        result = await sub_tools[tool_name](**tool_args)
                        result_str = json.dumps(result, ensure_ascii=False, default=str) if not isinstance(result, str) else result
                        tools_used.append(tool_name)
                        # 跟踪修改的文件
                        if tool_name in ("write_file", "edit_file") and "path" in tool_args:
                            files_modified.append(tool_args["path"])
                    except Exception as e:
                        result_str = f"[工具错误] {tool_name}: {e}"
                else:
                    result_str = f"[未知工具] {tool_name}"

                # 截断过长结果
                if len(result_str) > 2000:
                    result_str = result_str[:2000] + "\n... [已截断]"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str
                })

        if not final_reply:
            completed = False
            final_reply = "[达到最大工具调用轮数]"

        # P0: 简单任务结果校验 — 无效结果自动触发fallback
        simple_task = _is_simple_task(task)
        if simple_task and completed and final_reply:
            if not _validate_result(final_reply, task):
                logger.warning(f"简单任务结果无效，触发fallback: {task[:40]} -> {final_reply[:50]}")
                completed = False  # 触发下方fallback逻辑

        # P0: 非只读子代理完成后自动汇报变更摘要
        diff_summary = None
        if not spec.read_only and backup_info and backup_info.get("branch"):
            try:
                diff_summary = git_diff_summary(since_branch=backup_info["branch"])
            except Exception as e:
                logger.debug("caught exception: %s", e)
                diff_summary = None

        # P1: 自动验证修改的文件语法
        verification = None
        if not spec.read_only and tools_used:
            write_tools = {"write_file", "edit_file", "run_command"}
            if write_tools.intersection(tools_used):
                verification = self._auto_verify(tools_used)

        # P0: 模型fallback — 失败后升级模型重试（免费API，直接跳最强）
        task_status = "completed" if completed and final_reply else "failed"
        if task_status == "failed" and orchestrator:
            for fallback_attempt in range(2):
                fallback_client = orchestrator.get_fallback_client(fallback_attempt)
                if not fallback_client or fallback_client is client:
                    break
                logger.info(f"任务失败，fallback到: {fallback_client.model} (attempt {fallback_attempt+1})")
                client = fallback_client
                # 重置状态重跑
                messages = [{"role": "user", "content": task}]
                final_reply = ""
                completed = False
                tools_used = []
                tool_calls_log = []

                for turn in range(min(spec.max_turns, 50)):
                    try:
                        response = await client.chat(
                            messages=messages, system=system_prompt.strip(),
                            tools=tools_schema if tools_schema else None
                        )
                    except Exception as e:
                        final_reply = f"LLM调用失败: {e}"
                        # P0: fallback模型也记录健康度
                        if orchestrator:
                            try:
                                orchestrator.record_model_result(client.model, False)
                            except Exception as e:
                                logger.debug("caught exception: %s", e)
                        break

                    content = response.get("content", "") or ""
                    tool_calls = response.get("tool_calls", [])
                    if not tool_calls:
                        final_reply = content
                        completed = True
                        break

                    assistant_msg = {"role": "assistant", "content": content}
                    assistant_msg["tool_calls"] = [
                        {"id": tc["id"], "type": "function",
                         "function": {"name": tc["name"],
                                      "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                        for tc in tool_calls
                    ]
                    messages.append(assistant_msg)

                    for tc in tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc["arguments"]
                        tool_calls_log.append({"turn": turn, "tool": tool_name,
                            "args": {k: _safe_str(v, 100) for k, v in tool_args.items()}})
                        if tool_name in sub_tools:
                            try:
                                result = await sub_tools[tool_name](**tool_args)
                                result_str = json.dumps(result, ensure_ascii=False, default=str) if not isinstance(result, str) else result
                                tools_used.append(tool_name)
                            except Exception as e:
                                result_str = f"[工具错误] {tool_name}: {e}"
                        else:
                            result_str = f"[未知工具] {tool_name}"
                        if len(result_str) > 2000:
                            result_str = result_str[:2000] + "\n... [已截断]"
                        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_str})

                if not final_reply:
                    final_reply = "[达到最大工具调用轮数]"
                task_status = "completed" if completed and final_reply else "failed"
                if task_status == "completed":
                    break

        # P0: 记录模型健康度评分
        if orchestrator and client:
            try:
                orchestrator.record_model_result(client.model, task_status == "completed")
            except Exception as e:
                logger.debug("caught exception: %s", e)

        # 保存子代理独立记忆
        try:
            agent_memory_dir = AGENT_MEMORY_DIR
            agent_memory_dir.mkdir(parents=True, exist_ok=True)
            agent_memory_file = agent_memory_dir / f"{agent_type}_history.json"
            history = []
            if agent_memory_file.exists():
                history = json.loads(agent_memory_file.read_text(encoding="utf-8"))
            history.append({
                "task": task, "status": task_status,
                "tools_used": tools_used, "files_modified": files_modified,
                "time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            history = history[-20:]
            agent_memory_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"保存子代理记忆失败: {e}")

        # P1: 完成/失败进度
        self.progress(AgentProgressEvent(
            timestamp=datetime.now(), agent_name=spec.display_name,
            step="complete" if task_status == "completed" else "failed",
            status="success" if task_status == "completed" else "error",
            message=f"{'完成' if task_status == 'completed' else '失败'}: {final_reply[:60] if final_reply else '无输出'}",
            progress=100 if task_status == "completed" else progress_pct
        ))

        return {
            "agent_type": agent_type,
            "agent_name": spec.display_name,
            "task": task,
            "status": task_status,
            "summary": final_reply,
            "turns_used": turn + 1 if turn >= 0 else 0,
            "tools_used": tools_used,
            "tool_calls_log": tool_calls_log,
            "files_modified": files_modified,
            "backup_branch": backup_info.get("branch") if backup_info else None,
            "diff_summary": diff_summary,
            "verification": verification
        }

    def list_available_agents(self) -> List[Dict]:
        return self.registry.list_available()

    async def dispatch_parallel(self, tasks: List[Dict[str, Any]],
                                max_concurrent: int = 5) -> List[Dict[str, Any]]:
        """并行派遣多个子代理（Concurrent模式）"""
        from .parallel_core import AgentProgressEvent
        total = len(tasks)
        completed = [0]
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _bounded_dispatch(task_spec: Dict, idx: int) -> Dict:
            async with semaphore:
                agent_type = task_spec.pop("agent_type")
                result = await self.dispatch(agent_type=agent_type, **task_spec)
                completed[0] += 1
                # P1: 并行整体进度
                self.progress(AgentProgressEvent(
                    timestamp=datetime.now(), agent_name="并行调度",
                    step="complete", status="success",
                    message=f"完成 {completed[0]}/{total}: {agent_type} - {result.get('status', '?')}",
                    progress=int(completed[0] / total * 100)
                ))
                return result

        self.progress(AgentProgressEvent(
            timestamp=datetime.now(), agent_name="并行调度",
            step="start", status="running",
            message=f"启动 {total} 个并行任务", progress=0
        ))

        results = await asyncio.gather(
            *[_bounded_dispatch(dict(t), i) for i, t in enumerate(tasks)],
            return_exceptions=True
        )

        # 统一异常处理
        processed = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                processed.append({
                    "agent_type": tasks[i].get("agent_type", "unknown"),
                    "status": "failed",
                    "summary": f"[并行派遣异常] {type(r).__name__}: {r}",
                    "turns_used": 0
                })
            else:
                processed.append(r)

        return processed

    async def select_next_agent(self, task: str, context: str = "",
                                candidates: List[str] = None) -> Optional[str]:
        """LLM驱动的speaker选择（Group Chat模式）

        Args:
            task: 当前任务描述
            context: 已有上下文（已完成步骤等）
            candidates: 候选agent列表，None则用全部

        Returns:
            选中的agent_type，或None
        """
        from .parallel_core import _global_llm_client
        if not candidates:
            candidates = list(self.registry._BUILTIN_SPECS.keys())

        client = self._resolve_client(candidates[0]) or _global_llm_client
        if not client:
            return candidates[0] if candidates else None

        # 构造选择提示
        agent_list = []
        for name in candidates:
            spec = self.registry.get_spec(name)
            if spec:
                agent_list.append(f"- {name}: {spec.description}")

        prompt = f"""从以下子代理中选择最合适执行任务的一个：

【任务】{task}
【上下文】{context[:500] if context else '无'}

候选代理：
{chr(10).join(agent_list)}

只回复一个代理名称（如 xiaohuangmen），不要解释。"""

        try:
            result = await client.chat(
                messages=[{"role": "user", "content": prompt}],
                system="你是一个任务分发专家。根据任务描述选择最合适的子代理。",
                max_tokens=50, temperature=0.1
            )
            selected = result.get("content", "").strip().lower()
            # 精确匹配优先，再尝试子串
            # 构建 alias->canonical 映射
            alias_map = {a: c for a, c in self.registry._ALIASES.items()}
            # 精确匹配
            for name in candidates:
                if selected == name:
                    return name
            for alias, canonical in alias_map.items():
                if selected == alias:
                    return canonical
            # 子串匹配（候选名在LLM输出中，优先最长匹配）
            for name in sorted(candidates, key=len, reverse=True):
                if name in selected:
                    return name
            for alias, canonical in sorted(alias_map.items(), key=lambda x: len(x[0]), reverse=True):
                if alias in selected:
                    return canonical
            return candidates[0]
        except Exception as e:
            logger.warning(f"LLM选择失败: {e}")
            return candidates[0] if candidates else None

    # ── Handoff 模式 ──────────────────────────────────────────────

    async def dispatch_with_handoff(self, start_agent: str, task: str,
                                     handoff_rules: Dict[str, List[str]] = None,
                                     max_handoffs: int = 5,
                                     expected_output: str = None) -> Dict[str, Any]:
        """Handoff模式 — agent自主决定是否transfer给其他agent

        Args:
            start_agent: 起始agent类型
            task: 任务描述
            handoff_rules: {from_agent: [to_agents]} 转移规则
            max_handoffs: 最大转移次数
            expected_output: 期望输出

        Returns:
            最终agent的执行结果
        """
        current_agent = start_agent
        history = []
        result: Dict[str, Any] = {}

        for handoff_count in range(max(max_handoffs, 1)):
            spec = self.registry.get_spec(current_agent)
            if not spec:
                return {"error": f"Unknown agent: {current_agent}"}

            # 构造handoff指令
            handoff_targets = []
            if handoff_rules and current_agent in handoff_rules:
                handoff_targets = handoff_rules[current_agent]
            else:
                handoff_targets = [
                    name for name in self.registry._BUILTIN_SPECS.keys()
                    if name != current_agent
                ]

            handoff_hint = ""
            if handoff_targets:
                target_desc = []
                for t in handoff_targets:
                    s = self.registry.get_spec(t)
                    if s:
                        target_desc.append(f"  {t}: {s.description}")
                handoff_hint = f"""

【Handoff规则】如果你认为此任务应由其他代理处理，在回复末尾写：
HANDOFF:<agent_type>
可选目标：
{chr(10).join(target_desc)}
"""

            result = await self.dispatch(
                agent_type=current_agent,
                task=task,
                expected_output=expected_output,
                context=f"这是第{handoff_count + 1}轮。之前的代理历史：{json.dumps(history, ensure_ascii=False)[:500]}{handoff_hint}"
            )

            # 检查是否请求handoff（支持连字符的agent名）
            summary = result.get("summary", "")
            if "HANDOFF:" in summary:
                match = re.search(r'HANDOFF:[\w-]+', summary)
                if match:
                    target = match.group(0).split(":", 1)[1]
                    if target in self.registry._BUILTIN_SPECS:
                        logger.info(f"Handoff: {current_agent} -> {target}")
                        history.append({
                            "agent": current_agent,
                            "result": summary[:200],
                            "handoff_to": target
                        })
                        current_agent = target
                        continue

            # 无handoff，返回结果
            result["handoff_history"] = history
            result["total_handoffs"] = handoff_count
            return result

        # 超过最大handoff次数
        result["handoff_history"] = history
        result["total_handoffs"] = max_handoffs
        result["warning"] = "达到最大handoff次数"
        return result

    # ── Approval 模式 ──────────────────────────────────────────────

    async def dispatch_with_approval(self, agent_type: str, task: str,
                                      approval_reason: str = "",
                                      timeout: float = 300.0,
                                      **kwargs) -> Dict[str, Any]:
        """Human-in-the-loop — 执行前等待用户审批

        Args:
            agent_type: 子代理类型
            task: 任务描述
            approval_reason: 需要审批的原因
            timeout: 审批超时（秒）

        Returns:
            审批通过后执行结果，或审批拒绝/超时的结果
        """
        approval_id = str(_uuid.uuid4())[:8]

        # 创建 Future 用于等待审批结果
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        _pending_approvals[approval_id] = {
            "id": approval_id,
            "agent_type": agent_type,
            "task": task,
            "reason": approval_reason,
            "status": "pending",
            "future": future
        }

        logger.info(f"等待审批: {approval_id} - {agent_type}: {task[:50]}")

        # 等待审批结果（Future 被 approve() resolve）
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            _pending_approvals.pop(approval_id, None)
            return {
                "agent_type": agent_type,
                "status": "timeout",
                "summary": f"[审批超时] 任务 '{task[:50]}' 等待{timeout}秒未获审批",
                "approval_id": approval_id
            }

        # 清理已审批项
        _pending_approvals.pop(approval_id, None)

        if not result.get("approved"):
            return {
                "agent_type": agent_type,
                "status": "rejected",
                "summary": f"[审批拒绝] {result.get('reason', '用户拒绝')}",
                "approval_id": approval_id
            }

        # 审批通过，执行任务
        return await self.dispatch(agent_type=agent_type, task=task, **kwargs)

    def approve(self, approval_id: str, approved: bool = True, reason: str = ""):
        """提交审批结果（供外部调用，resolve Future）"""
        entry = _pending_approvals.get(approval_id)
        if entry and not entry["future"].done():
            entry["future"].set_result({"approved": approved, "reason": reason})

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """获取待审批列表（非破坏性读取）"""
        return [
            {"id": k, "agent_type": v["agent_type"], "task": v["task"],
             "reason": v["reason"], "status": v["status"]}
            for k, v in _pending_approvals.items()
            if not v["future"].done()
        ]

    # ── 迭代精炼模式 ──────────────────────────────────────────────

    async def dispatch_iterative_refine(self, writer_agent: str, reviewer_agent: str,
                                         task: str, max_rounds: int = 3,
                                         quality_threshold: float = 0.8) -> Dict[str, Any]:
        """多轮迭代精炼（Group Chat模式 — writer-reviewer循环）"""
        from .refine import dispatch_iterative_refine_impl
        return await dispatch_iterative_refine_impl(
            dispatcher=self,
            writer_agent=writer_agent,
            reviewer_agent=reviewer_agent,
            task=task,
            max_rounds=max_rounds,
            quality_threshold=quality_threshold
        )

    def get_progress_dashboard(self) -> Dict[str, Any]:
        """进度看板 — 实时显示plan/ledger/stall状态（Magentic模式）"""
        from ...state.task_plan import TaskPlanManager
        from ...state.task_state import get_task_state_manager

        state_mgr = get_task_state_manager()
        progress = state_mgr.get_progress()

        # 使用单例 TaskPlanManager 避免重复加载磁盘
        if not hasattr(self, '_plan_mgr'):
            self._plan_mgr = TaskPlanManager(state_mgr)

        plans_status = []
        for plan_id, plan in self._plan_mgr.plans.items():
            plans_status.append(self._plan_mgr.get_plan_status(plan_id))

        return {
            "progress": progress,
            "plans": plans_status,
            "pending_approvals": self.get_pending_approvals()
        }
