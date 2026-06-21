#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SearXNG Knowledge Collector for AI Knowledge Base
基于SearXNG联网搜索，收集整理知识，导入LLM Wiki+Obsidian
"""

import requests
import json
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import re

# Windows UTF-8支持
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'ignore')

class SearXNGCollector:
    """SearXNG知识收集器"""

    def __init__(self, searxng_url: str = "http://localhost:8080",
                 llmwiki_project: str = None):
        """
        初始化收集器

        Args:
            searxng_url: SearXNG实例URL (默认本地8080)
            llmwiki_project: LLM Wiki项目目录
        """
        self.searxng_url = searxng_url.rstrip('/')
        self.llmwiki_project = Path(llmwiki_project) if llmwiki_project else None

        # 知识库目录结构
        if self.llmwiki_project:
            self.import_dir = self.llmwiki_project / "Import"
            self.wiki_dir = self.llmwiki_project / "wiki"
            self.import_dir.mkdir(parents=True, exist_ok=True)
            self.wiki_dir.mkdir(parents=True, exist_ok=True)

    def search_wikipedia_category(self, category: str,
                                 lang: str = "zh") -> List[Dict]:
        """
        搜索维基百科指定分类的内容

        Args:
            category: 维基分类名称 (如: 电机工程)
            lang: 语言代码 (zh, en等)

        Returns:
            搜索结果列表
        """
        print(f"🔍 正在搜索维基百科分类: {category}")

        # SearXNG搜索查询 - 专门针对维基百科分类页面
        queries = [
            f"site:zh.wikipedia.org Category:{category}",
            f"site:zh.wikipedia.org {category}",
            f"{category} 维基百科",
            f"{category} wiki"
        ]

        results = []
        for query in queries:
            print(f"  查询: {query}")
            try:
                res = self._search_searxng(query, lang=lang)
                if res:
                    results.extend(res)
                time.sleep(1)  # 礼貌延迟
            except Exception as e:
                print(f"  警告: 查询失败 - {e}")

        # 去重
        unique = []
        seen = set()
        for r in results:
            key = r.get('url', r.get('title', ''))
            if key and key not in seen:
                seen.add(key)
                unique.append(r)

        print(f"✅ 找到 {len(unique)} 个独特结果")
        return unique

    def _search_searxng(self, query: str, lang: str = "zh",
                       categories: List[str] = None) -> List[Dict]:
        """
        执行SearXNG搜索

        Args:
            query: 搜索查询
            lang: 语言
            categories: 限制搜索分类 (如 ['images', 'videos'])

        Returns:
            结果列表
        """
        params = {
            'q': query,
            'format': 'json',
            'language': lang,
            'page': 1,
            'pageno': 1,
        }

        if categories:
            params['category'] = ','.join(categories)

        try:
            response = requests.get(f"{self.searxng_url}/search",
                                  params=params, timeout=10)
            if response.status_code != 200:
                print(f"  SearXNG错误: HTTP {response.status_code}")
                return []

            data = response.json()

            results = []
            for result in data.get('results', []):
                results.append({
                    'title': result.get('title', ''),
                    'url': result.get('url', ''),
                    'content': result.get('content', ''),
                    'source': result.get('source', ''),
                    'category': 'web'
                })

            return results

        except requests.RequestException as e:
            print(f"  连接SearXNG失败: {e}")
            return []

    def fetch_wikipedia_page(self, url: str) -> Dict[str, Any]:
        """
        获取维基百科页面内容 (通过SearXNG或直接)
        """
        print(f"  📖 获取页面: {url}")

        try:
            # 尝试直接获取 (维基百科允许)
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return {'error': f'HTTP {response.status_code}'}

            # 简单提取 - 实际需要HTML解析
            content = response.text

            # 提取标题 (从HTML)
            title_match = re.search(r'<title>(.+?) - 维基百科</title>', content)
            title = title_match.group(1) if title_match else "Unknown"

            # 清理HTML获取纯文本 (简化版)
            # 实际应该用BeautifulSoup
            text = re.sub(r'<[^>]+>', ' ', content)
            text = re.sub(r'\s+', ' ', text).strip()
            text = text[:5000]  # 限制长度

            return {
                'title': title,
                'url': url,
                'content': text[:3000],
                'source': 'zh.wikipedia.org',
                'fetched_at': datetime.now().isoformat()
            }

        except Exception as e:
            return {'error': str(e)}

    def enrich_with_claude(self, search_results: List[Dict]) -> List[Dict]:
        """
        使用Claude API丰富搜索结果 (需要配置Claude Desktop API)
        """
        print("🧠 使用Claude API丰富内容...")

        try:
            from .claude_enricher import ClaudeEnricher
            enricher = ClaudeEnricher()

            enriched = []
            for result in search_results[:10]:  # 限制数量避免API成本
                print(f"  处理: {result.get('title', '')[:50]}...")
                enriched_content = enricher.enrich(result)
                enriched.append({**result, **enriched_content})
                time.sleep(0.5)

            return enriched

        except ImportError:
            print("  ⚠️  ClaudeEnricher不可用，跳过丰富步骤")
            return search_results

    def generate_markdown_document(self, item: Dict,
                                  category: str) -> str:
        """
        为搜索结果生成Markdown文档 (LLM Wiki格式)
        """
        title = item.get('title', 'Untitled')
        url = item.get('url', '')
        content = item.get('content', '')
        summary = item.get('summary', '')

        # 提取标签/实体
        tags = ['电机工程', '电气工程', '维基百科']
        if 'category' in item:
            tags.append(item['category'])

        # 提取关键概念 (简化版 - 实际应使用NLP)
        concepts = self._extract_concepts(content)

        markdown = f"""---
title: {title}
source: {url}
category: KnowledgeBase
tags: {json.dumps(tags, ensure_ascii=False)}
entities: {json.dumps(list(concepts)[:10], ensure_ascii=False)}
created: {datetime.now().strftime('%Y-%m-%d')}
---

# {title}

## 摘要

{summary or content[:500]}

## 详细内容

{content[:3000]}

## 来源

**原始链接**: [{url}]({url})

**来源类型**: 维基百科

**采集时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

*本文档由SearXNG知识收集器自动生成，用于丰富AI知识库。*
"""
        return markdown

    def _extract_concepts(self, text: str) -> set:
        """提取关键概念 (简单关键词提取)"""
        # 移除停用词
        stopwords = {'的', '了', '和', '与', '或', '在', '是', '有', '为', '对',
                     'the', 'and', 'or', 'in', 'is', 'are', 'to', 'of', 'a'}

        words = re.findall(r'[一-鿿]+|[a-zA-Z]+', text.lower())
        concepts = set()

        for word in words:
            if len(word) > 1 and word not in stopwords:
                concepts.add(word)

        return concepts

    def save_to_import(self, documents: List[str],
                      category: str = "wikipedia"):
        """
        保存到LLM Wiki的Import目录
        """
        if not self.llmwiki_project:
            print("❌ 未配置LLM Wiki项目目录")
            return

        saved = 0
        for i, doc in enumerate(documents):
            filename = f"searxng-{category}-{i+1:03d}-{datetime.now().strftime('%Y%m%d')}.md"
            filepath = self.import_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(doc)

            print(f"  ✓ 保存: {filename}")
            saved += 1

        print(f"✅ 已保存 {saved} 个文档到 {self.import_dir}")
        return saved

    def run_collection(self, category: str,
                      max_results: int = 20,
                      enrich: bool = False):
        """
        执行完整的知识收集流程

        Args:
            category: 维基分类名称
            max_results: 最大结果数
            enrich: 是否使用Claude API丰富内容
        """
        print("=" * 60)
        print(f"  SearXNG知识收集器")
        print(f"  目标分类: {category}")
        print("=" * 60)

        # 1. 搜索
        results = self.search_wikipedia_category(category)
        results = results[:max_results]

        if not results:
            print("❌ 未找到任何结果")
            return

        # 2. 获取页面内容
        documents = []
        for result in results:
            if 'wikipedia.org' in result.get('url', ''):
                page_data = self.fetch_wikipedia_page(result['url'])
                if 'error' not in page_data:
                    result.update(page_data)

            documents.append(result)

        # 3. 可选Claude丰富
        if enrich:
            documents = self.enrich_with_claude(documents)

        # 4. 生成Markdown
        markdown_docs = []
        for doc in documents:
            md = self.generate_markdown_document(doc, category)
            markdown_docs.append(md)

        # 5. 保存
        saved = self.save_to_import(markdown_docs, category)

        print("\n" + "=" * 60)
        print(f"✅ 收集完成！")
        print(f"   搜索到: {len(results)} 个结果")
        print(f"   生成文档: {len(markdown_docs)} 个")
        print(f"   保存到: {self.import_dir}")
        print("\n下一步: 在LLM Wiki中导入这些文件，或在Obsidian中查看")
        print("=" * 60)


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="SearXNG知识收集器 - 丰富AI知识库")
    parser.add_argument('--searxng-url', default='http://localhost:8080',
                       help='SearXNG实例URL')
    parser.add_argument('--llmwiki-dir',
                       help='LLM Wiki项目目录 (指定Import文件夹位置)')
    parser.add_argument('--category', required=True,
                       help='维基百科分类名称 (如: 电机工程)')
    parser.add_argument('--max-results', type=int, default=20,
                       help='最大结果数量')
    parser.add_argument('--enrich', action='store_true',
                       help='使用Claude API丰富内容')
    parser.add_argument('--output',
                       help='输出目录 (独立于LLM Wiki)')

    args = parser.parse_args()

    collector = SearXNGCollector(
        searxng_url=args.searxng_url,
        llmwiki_project=args.llmwiki_dir
    )

    collector.run_collection(
        category=args.category,
        max_results=args.max_results,
        enrich=args.enrich
    )


if __name__ == "__main__":
    # 快速测试
    collector = SearXNGCollector(
        searxng_url="http://localhost:8080",
        llmwiki_project="D:/KnowledgeBase/MyWiki"
    )

    # 搜索电机工程内容
    collector.run_collection(
        category="电机工程",
        max_results=15,
        enrich=False
    )