#!/usr/bin/env python3
"""DeepWiki 完整索引抓取工具 - 基于公开站点地图合规拉取所有已收录项目"""

import requests
import xml.etree.ElementTree as ET
import time
import csv
import json
import os
from pathlib import Path

# 站点地图的XML命名空间
NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
# 请求限速（每个请求间隔1秒，完全符合爬虫友好规则）
REQUEST_DELAY = 1.0
# 超时时间
TIMEOUT = 15
# 输出目录
OUTPUT_DIR = Path("AI知识库/raw/sources/deepwiki")
# User-Agent
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KnowledgeBot/1.0)"}


def fetch_and_parse(url, is_root=False):
    """拉取并解析站点地图"""
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        if is_root:
            sub_sitemaps = []
            for sitemap in root.findall("sm:sitemap", NAMESPACE):
                loc = sitemap.find("sm:loc", NAMESPACE).text
                sub_sitemaps.append(loc)
            return sub_sitemaps
        else:
            projects = []
            for url_elem in root.findall("sm:url", NAMESPACE):
                loc = url_elem.find("sm:loc", NAMESPACE).text
                parts = loc.strip("/").split("/")
                if len(parts) >= 2:
                    owner = parts[-2]
                    repo = parts[-1]
                    lastmod_elem = url_elem.find("sm:lastmod", NAMESPACE)
                    lastmod = lastmod_elem.text if lastmod_elem else None
                    projects.append({
                        "url": loc,
                        "owner": owner,
                        "repo": repo,
                        "last_modified": lastmod
                    })
            return projects
    except Exception as e:
        print(f"  [WARN] 处理 {url} 失败: {e}")
        return []


def main():
    print("=" * 60)
    print("DeepWiki 完整索引抓取工具")
    print("基于公开站点地图，合规拉取所有已收录项目")
    print("=" * 60)

    # 确保输出目录存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 拉取根站点地图
    print("\n[1/3] 拉取根站点地图...")
    root_sitemap_url = "https://deepwiki.com/sitemap.xml"
    sub_sitemaps = fetch_and_parse(root_sitemap_url, is_root=True)
    print(f"找到 {len(sub_sitemaps)} 个分站点地图")

    if not sub_sitemaps:
        print("未找到分站点地图，可能站点地图结构已变化")
        return

    # 2. 批量拉取所有分站点地图
    print(f"\n[2/3] 批量拉取 {len(sub_sitemaps)} 个分站点地图（限速 1s/请求）...")
    all_projects = []
    failed = 0
    for i, sub_url in enumerate(sub_sitemaps, 1):
        projects = fetch_and_parse(sub_url)
        if projects:
            all_projects.extend(projects)
        else:
            failed += 1
        # 进度显示
        if i % 10 == 0 or i == len(sub_sitemaps):
            print(f"  进度: {i}/{len(sub_sitemaps)} | 已获取: {len(all_projects)} 项目 | 失败: {failed}")
        time.sleep(REQUEST_DELAY)

    # 3. 去重并保存
    print("\n[3/3] 整理并保存索引...")
    unique_projects = {p["url"]: p for p in all_projects}.values()
    sorted_projects = sorted(unique_projects, key=lambda x: (x["owner"], x["repo"]))

    # 保存CSV
    csv_path = OUTPUT_DIR / "deepwiki_index.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["owner", "repo", "url", "last_modified"])
        writer.writeheader()
        writer.writerows(sorted_projects)

    # 保存JSON（方便程序读取）
    json_path = OUTPUT_DIR / "deepwiki_index.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sorted_projects, f, ensure_ascii=False, indent=2)

    # 保存为Markdown索引（方便AI读取）
    md_path = OUTPUT_DIR / "INDEX.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# DeepWiki 项目索引\n\n")
        f.write(f"抓取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"项目总数: {len(sorted_projects)}\n\n")
        f.write("| Owner | Repo | URL | Last Modified |\n")
        f.write("|-------|------|-----|---------------|\n")
        for p in sorted_projects:
            f.write(f"| {p['owner']} | {p['repo']} | {p['url']} | {p['last_modified'] or 'N/A'} |\n")

    # 统计信息
    owners = set(p["owner"] for p in sorted_projects)
    print(f"\n{'=' * 60}")
    print(f"抓取完成!")
    print(f"  项目总数: {len(sorted_projects)}")
    print(f"  独立作者/组织: {len(owners)}")
    print(f"  分站点地图: {len(sub_sitemaps)} (失败: {failed})")
    print(f"\n输出文件:")
    print(f"  CSV:  {csv_path}")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
