"""kb_llm.py - LLM API integration for Knowledge Base Manager

Provides Claude/OpenAI API calls via KBLlmMixin: document analysis,
reranking, and answer generation.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from i18n import t
from .kb_utils import _get_file_hash

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("警告: openai库未安装，请运行: pip install openai")


class KBLlmMixin:
    """Mixin: LLM API calls (analysis, reranking, answer generation)."""

    def _get_client(self):
        """Get OpenAI-compatible client (supports NVIDIA API and other providers)"""
        api_key = self.config.get("api_key", "")
        base_url = self.config.get("base_url", "https://integrate.api.nvidia.com/v1")
        if not api_key:
            raise ValueError(t('error.api_key_missing'))
        return OpenAI(api_key=api_key, base_url=base_url)

    def _get_model(self) -> str:
        """Get model name (unified default)"""
        return self.config.get("model", "stepfun-ai/step-3.7-flash")

    def _analyze_with_claude(self, content: str, filename: str, existing_index: Optional[Dict] = None) -> Dict[str, Any]:
        """Analyze document content with LLM (auto-classify + bidirectional links + structured breakdown)"""
        client = self._get_client()

        # Build context from existing index for automatic link matching
        existing_context = ""
        if existing_index and existing_index.get("documents"):
            titles = [d["title"] for d in existing_index["documents"][-30:]]
            concepts = list(existing_index.get("concepts", {}).keys())[:20]
            existing_context = f"""
已有知识库条目（用于匹配双向链接）:
标题: {', '.join(titles)}
已有概念: {', '.join(concepts)}
"""

        prompt = f"""请分析以下文档内容，提取关键信息并以JSON格式返回。

文档名称: {filename}
{existing_context}

要求返回的JSON结构:
{{
    "title": "文档标题（简洁明了）",
    "summary": "2-3句话摘要（100字以内）",
    "concepts": ["关键概念1", "关键概念2", ...],
    "entities": ["实体名称1", "实体名称2", ...],
    "tags": ["标签1", "标签2", ...],
    "category": "文档类别（从以下选择：AI/编程/领域/工具/参考）",
    "suggested_links": ["从已有知识库中匹配的相关标题，精确匹配"],
    "key_points": ["核心观点1", "核心观点2", ...],
    "structured_breakdown": {{
        "core_idea": "一句话核心观点",
        "detailed_explanation": "详细推导或解释（200字以内）",
        "code_examples": ["相关代码示例或伪代码"],
        "applicable_scenarios": ["适用场景"],
        "common_mistakes": ["常见误区"]
    }},
    "missing_concepts": ["文中提到但知识库可能没有的基础概念，用于自动补全"]
}}

文档内容:
{content[:4000]}

请确保返回的是有效的JSON格式，不要包含其他解释文字。"""

        response = client.chat.completions.create(
            model=self._get_model(),
            max_tokens=self.config.get("max_tokens", 4096),
            temperature=0.3,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        result_text = response.choices[0].message.content

        # Try to extract JSON
        json_match = re.search(r'```json\n?(.*?)\n```', result_text, re.DOTALL)
        if json_match:
            result_text = json_match.group(1)

        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            # Return basic structure on JSON parse failure
            return {
                "title": filename,
                "summary": "自动生成的摘要",
                "concepts": [],
                "entities": [],
                "tags": [],
                "suggested_links": [],
                "category": "其他",
                "key_points": [],
                "structured_breakdown": {},
                "missing_concepts": []
            }

    def _rerank(self, question: str, candidates: list, limit: int) -> list:
        """Use AI to rerank candidate results by relevance"""
        client = self._get_client()
        titles = [c["doc"]["title"] for c in candidates]
        summaries = [c["doc"].get("summary", "")[:100] for c in candidates]

        items_text = "\n".join([f"{i+1}. {t_} - {s}" for i, (t_, s) in enumerate(zip(titles, summaries))])

        prompt = f"""对以下知识库文档按与问题的相关性排序，返回最相关的{limit}个文档编号（逗号分隔）。

问题: {question}

文档列表:
{items_text}

只返回编号，如: 2,1,5"""

        response = client.chat.completions.create(
            model=self._get_model(),
            max_tokens=50,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        result = response.choices[0].message.content.strip()
        try:
            indices = [int(x.strip()) - 1 for x in result.split(",") if x.strip().isdigit()]
            seen = set()
            reranked = []
            for i in indices:
                if 0 <= i < len(candidates) and i not in seen:
                    seen.add(i)
                    reranked.append(candidates[i])
            return reranked[:limit] if reranked else candidates[:limit]
        except (ValueError, IndexError):
            return candidates[:limit]

    def _generate_answer(self, question: str, contexts: List[str]) -> str:
        """Generate answer using LLM"""
        client = self._get_client()

        context_text = "\n\n".join(contexts[:3])

        prompt = f"""基于以下知识库文档内容，回答用户问题。如果文档中没有相关信息，请说明。

知识库文档:
{context_text}

用户问题: {question}

请提供准确、简洁的回答，并在回答中标注参考了哪个文档。"""

        response = client.chat.completions.create(
            model=self._get_model(),
            max_tokens=1500,
            temperature=0.3,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        return response.choices[0].message.content
