"""上下文构建逻辑 — _build_shared_context + _filter_relevance

从 dispatcher.py 拆出，作为 Mixin 混入 SubagentDispatcher。
"""

import re
import json
import asyncio
import logging
from typing import Set

logger = logging.getLogger(__name__)


class ContextMixin:
    """提供 _build_shared_context 和 _filter_relevance 方法"""

    async def _build_shared_context(self, task: str, user_context: str = None,
                                     agent_type: str = None) -> str:
        """构建共享上下文 — 异步 + 相关性过滤"""
        from ...config import AGENT_MEMORY_DIR
        from .approval import _kb_query_sync

        parts = []
        task_words = set(task.lower().split())

        # 1. 子代理独立记忆
        if agent_type:
            try:
                agent_memory_dir = AGENT_MEMORY_DIR
                agent_memory_file = agent_memory_dir / f"{agent_type}_history.json"
                if agent_memory_file.exists():
                    history = json.loads(agent_memory_file.read_text(encoding="utf-8"))
                    if history:
                        recent_records = history[-5:]
                        mem_lines = []
                        for rec in recent_records:
                            mem_lines.append(f"  [{rec.get('time', '?')}] {rec.get('task', '')[:80]} -> {rec.get('status', '?')}")
                        parts.append(f"【子代理历史记忆】\n" + "\n".join(mem_lines))
            except Exception as e:
                logger.warning(f"读取子代理记忆失败: {e}")

        # 2. 用户显式传入的上下文
        if user_context:
            parts.append(f"【上下文】\n{user_context}")

        # 3. 从MemoryStore提取（带相关性过滤）
        if self.memory:
            try:
                long_term = await asyncio.to_thread(self.memory.get_long_term_memory)
                if long_term and long_term != "暂无内容，将在压缩时自动生成。":
                    # 相关性过滤：只保留与任务关键词相关的内容
                    filtered = self._filter_relevance(long_term, task_words, max_chars=800)
                    if filtered:
                        parts.append(f"【长期记忆】\n{filtered}")
            except Exception as e:
                logger.warning(f"读取长期记忆失败: {e}")

            try:
                recent = await asyncio.to_thread(self.memory.get_recent_history, limit=6)
                if recent:
                    summary_lines = []
                    for msg in recent[-6:]:
                        if not isinstance(msg, dict):
                            continue
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")[:150]
                        # 相关性过滤：跳过完全无关的对话
                        if task_words and not any(w in content.lower() for w in task_words):
                            continue
                        summary_lines.append(f"  [{role}] {content}")
                    if summary_lines:
                        parts.append(f"【最近对话】\n" + "\n".join(summary_lines[:4]))
            except Exception as e:
                logger.warning(f"读取最近对话失败: {e}")

        # 3. 知识库相关文档（异步包装同步IO）
        try:
            kb_results = await asyncio.to_thread(_kb_query_sync, task, 2)
            if kb_results:
                kb_context = "\n".join(
                    f"  - {r['title']}: {r.get('summary', '')[:200]}"
                    for r in kb_results
                )
                parts.append(f"【相关知识库文档】\n{kb_context}")
        except Exception as e:
            logger.warning(f"KB查询失败: {e}")

        return "\n\n".join(parts) if parts else ""

    def _filter_relevance(self, text: str, task_words: Set[str],
                          max_chars: int = 800) -> str:
        """按关键词相关性过滤长文本"""
        if not task_words:
            return text[:max_chars]

        # 按句子分割，只保留包含任务关键词的句子
        sentences = re.split(r'[。！？\n]+', text)
        relevant = []
        total = 0
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            # 如果句子包含任何任务关键词，或当前相关句子较少，保留
            if any(w in sent.lower() for w in task_words) or len(relevant) < 3:
                relevant.append(sent)
                total += len(sent)
                if total >= max_chars:
                    break

        return "。".join(relevant)[:max_chars]
