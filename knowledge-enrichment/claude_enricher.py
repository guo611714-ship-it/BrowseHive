#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude API Enricher for SearXNG Results
使用Claude API增强搜索结果，生成结构化知识文档
"""

import os
import json
from typing import Dict, Any
from datetime import datetime

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class ClaudeEnricher:
    """使用Claude API丰富搜索内容"""

    def __init__(self, api_key: str = None, model: str = "clude-sonnet-4-20250514"):
        """
        初始化Claude丰富器

        Args:
            api_key: Claude API密钥 (可选，默认从环境变量读取)
            model: 使用的Claude模型
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model

        if not self.api_key:
            raise ValueError("未设置ANTHROPIC_API_KEY，请设置环境变量或传入api_key参数")

        if not ANTHROPIC_AVAILABLE:
            raise ImportError("请安装anthropic: pip install anthropic")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def enrich(self, search_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        丰富单个搜索结果

        Args:
            search_result: 原始搜索结果 (包含title, content, url等)

        Returns:
            丰富后的结果 (添加summary, concepts, entities, tags等)
        """
        title = search_result.get('title', '')
        content = search_result.get('content', search_result.get('raw_content', ''))[:3000]
        url = search_result.get('url', '')

        if not content:
            print(f"  ⚠️  跳过 (无内容): {title[:50]}")
            return search_result

        prompt = f"""请分析以下从互联网搜索获取的关于"电机工程"的文档，进行知识提取和结构化。

原始文档:
标题: {title}
来源: {url}
内容:
{content}

请以JSON格式返回以下信息 (不要有其他文字):
{{
    "summary": "2-3句话的专业摘要，突出关键技术点",
    "key_concepts": ["核心概念1", "核心概念2", ...],
    "entities": ["实体名1(如: 变压器、异步电机)", "实体名2", ...],
    "technical_terms": ["术语1", "术语2", ...],
    "domain": "电机工程|电力系统|电子技术|自动化|其他",
    "relevance_score": 0.0-1.0 (与电机工程的相关度),
    "category": "理论|应用|设备|标准|历史|其他",
    "suggested_tags": ["标签1", "标签2", ...]
}}

要求:
- summary: 用中文，技术准确，简洁明了
- key_concepts: 提取3-8个关键技术概念
- entities: 提取具体的设备、材料、人名、公司等
- technical_terms: 提取专业术语
- relevance_score: 0.0(不相关) 到 1.0(高度相关)
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            result_text = response.content[0].text.strip()

            # 提取JSON
            import re
            json_match = re.search(r'```json\n?(.*?)\n```', result_text, re.DOTALL)
            if json_match:
                result_text = json_match.group(1)

            enrichment = json.loads(result_text)

            # 合并回原始结果
            enriched = {**search_result, **enrichment}
            print(f"  ✓ 已丰富: {title[:50]}")
            return enriched

        except Exception as e:
            print(f"  ❌ 丰富失败 ({title[:50]}): {e}")
            return search_result

    def batch_enrich(self, results: List[Dict[str, Any]],
                    delay: float = 0.5) -> List[Dict[str, Any]]:
        """
        批量丰富搜索结果

        Args:
            results: 搜索结果列表
            delay: API调用间隔 (秒)，避免触发限流

        Returns:
            丰富后的结果列表
        """
        print(f"🧠 开始批量丰富 {len(results)} 个结果...")
        enriched = []

        for i, result in enumerate(results, 1):
            print(f"[{i}/{len(results)}] ", end='')
            enriched_result = self.enrich(result)
            enriched.append(enriched_result)

            if i < len(results):
                time.sleep(delay)

        print(f"✅ 批量丰富完成")
        return enriched


def main():
    """测试函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Claude内容丰富器")
    parser.add_argument('--input', required=True, help='输入JSON文件 (搜索结果)')
    parser.add_argument('--output', help='输出JSON文件 (默认: input-enriched.json)')
    parser.add_argument('--api-key', help='Claude API密钥')

    args = parser.parse_args()

    # 加载搜索结果
    with open(args.input, 'r', encoding='utf-8') as f:
        results = json.load(f)

    # 初始化丰富器
    enricher = ClaudeEnricher(api_key=args.api_key)

    # 批量处理
    enriched = enricher.batch_enrich(results)

    # 保存
    output_file = args.output or args.input.replace('.json', '-enriched.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    print(f"📁 已保存: {output_file}")


if __name__ == "__main__":
    # 测试
    test_result = {
        "title": "电动机 - 维基百科",
        "url": "https://zh.wikipedia.org/wiki/电动机",
        "content": "电动机，也被称为电机，是一种将电能转换为机械能的设备..."
    }

    try:
        enricher = ClaudeEnricher()
        enriched = enricher.enrich(test_result)
        print(json.dumps(enriched, indent=2, ensure_ascii=False))
    except ValueError as e:
        print(f"需要设置ANTHROPIC_API_KEY环境变量: {e}")