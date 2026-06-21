"""DeepWiki 索引工具 - 基于公开站点地图抓取GitHub项目索引"""

import asyncio
import csv
import heapq
import json
import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict
from .tool_registry import tool, cached
from ..config import AI_KNOWLEDGE_BASE

logger = logging.getLogger(__name__)

try:
    import requests as _requests
except ImportError:
    _requests = None  # 延迟报错，工具调用时再检查

# 站点地图XML命名空间
_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
# 请求限速（秒）
_REQUEST_DELAY = 1.0
_TIMEOUT = 15
_MAX_RETRIES = 3
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; KnowledgeBot/1.0)"}

# 索引输出目录
_INDEX_DIR = AI_KNOWLEDGE_BASE / "raw" / "sources" / "deepwiki"

# 内存缓存（避免重复读盘）
_index_cache: Dict[str, list] = {}
_cache_mtime: float = 0.0


def _fetch_url(url: str):
    """拉取URL并返回响应（同步，带重试）"""
    if _requests is None:
        raise ImportError("requests 未安装，请运行: pip install requests")
    last_err = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = _requests.get(url, timeout=_TIMEOUT, headers=_HEADERS)
            resp.raise_for_status()
            return resp
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2 ** attempt)  # 指数退避
    raise last_err


async def _async_fetch(url: str):
    """异步HTTP请求（通过线程池避免阻塞事件循环）"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_url, url)


def _parse_root_sitemap(content: bytes) -> List[str]:
    """解析根站点地图，返回分站点地图URL列表"""
    root = ET.fromstring(content)
    sub_sitemaps = []
    for sitemap in root.findall("sm:sitemap", _NAMESPACE):
        loc_elem = sitemap.find("sm:loc", _NAMESPACE)
        if loc_elem is not None and loc_elem.text:
            sub_sitemaps.append(loc_elem.text.strip())
    return sub_sitemaps


def _parse_sub_sitemap(content: bytes) -> List[Dict]:
    """解析分站点地图，返回项目列表"""
    root = ET.fromstring(content)
    projects = []
    for url_elem in root.findall("sm:url", _NAMESPACE):
        loc_elem = url_elem.find("sm:loc", _NAMESPACE)
        if loc_elem is None or not loc_elem.text:
            continue
        loc = loc_elem.text.strip()
        # 提取 owner/repo：URL格式为 https://deepwiki.com/{owner}/{repo}
        # 过滤掉协议、空段、域名，只保留路径部分
        path = [p for p in loc.rstrip("/").split("/") if p and p not in ("https:", "http:", "")]
        # 域名之后必须恰好有 owner 和 repo 两段
        # path 格式: ["deepwiki.com", "owner", "repo"]
        if len(path) != 3 or not path[1] or not path[2]:
            continue
        owner, repo = path[1], path[2]
        lastmod_elem = url_elem.find("sm:lastmod", _NAMESPACE)
        lastmod = lastmod_elem.text if lastmod_elem is not None and lastmod_elem.text else None
        projects.append({
            "url": loc,
            "owner": owner,
            "repo": repo,
            "last_modified": lastmod,
        })
    return projects


def _load_index() -> list:
    """加载索引JSON，带内存缓存（检测文件修改时间）"""
    global _index_cache, _cache_mtime
    json_path = _INDEX_DIR / "deepwiki_index.json"
    if not json_path.exists():
        return []
    mtime = json_path.stat().st_mtime
    if mtime != _cache_mtime or "data" not in _index_cache:
        with open(json_path, encoding="utf-8") as f:
            _index_cache["data"] = json.load(f)
        _cache_mtime = mtime
    return _index_cache["data"]


@tool("deepwiki_fetch_index", "从DeepWiki站点地图抓取所有已收录的GitHub项目索引。返回项目列表(owner/repo/url/lastmod)并保存CSV/JSON/MD到AI知识库。")
async def deepwiki_fetch_index(max_pages: int = 500) -> dict:
    """抓取DeepWiki完整项目索引

    :param max_pages: 最多拉取的分站点地图数量，范围1-2000，默认500
    """
    # 参数校验
    max_pages = max(1, min(max_pages, 2000))
    t0 = time.time()

    # 1. 拉取根站点地图
    try:
        resp = await _async_fetch("https://deepwiki.com/sitemap.xml")
        sub_sitemaps = _parse_root_sitemap(resp.content)
    except Exception as e:
        return {"code": 500, "msg": f"拉取根站点地图失败: {e}", "data": {}}

    if not sub_sitemaps:
        return {"code": 404, "msg": "未找到分站点地图", "data": {}}

    # 限制数量
    sub_sitemaps = sub_sitemaps[:max_pages]

    # 2. 批量拉取分站点地图
    all_projects = []
    failed = 0
    for i, sub_url in enumerate(sub_sitemaps, 1):
        try:
            resp = await _async_fetch(sub_url)
            projects = _parse_sub_sitemap(resp.content)
            all_projects.extend(projects)
        except Exception as e:
            logger.debug("子站点地图拉取失败: %s", e)
            failed += 1
        if i % 10 == 0:
            logger.info("deepwiki progress: %d/%d | projects: %d | failed: %d",
                        i, len(sub_sitemaps), len(all_projects), failed)
        await asyncio.sleep(_REQUEST_DELAY)

    # 3. 去重
    unique = {p["url"]: p for p in all_projects}.values()
    sorted_projects = sorted(unique, key=lambda x: (x["owner"], x["repo"]))

    # 4. 保存文件（用 run_in_executor 避免阻塞事件循环）
    _INDEX_DIR.mkdir(parents=True, exist_ok=True)

    # 先失效缓存，防止其他协程读到旧数据
    global _cache_mtime
    _cache_mtime = 0.0

    def _write_files():
        csv_path = _INDEX_DIR / "deepwiki_index.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["owner", "repo", "url", "last_modified"])
            writer.writeheader()
            writer.writerows(sorted_projects)

        json_path = _INDEX_DIR / "deepwiki_index.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(sorted_projects, f, ensure_ascii=False, indent=2)

        md_path = _INDEX_DIR / "INDEX.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# DeepWiki 项目索引\n\n")
            f.write(f"抓取时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"项目总数: {len(sorted_projects)}\n\n")
            f.write("| Owner | Repo | URL | Last Modified |\n")
            f.write("|-------|------|-----|---------------|\n")
            for p in sorted_projects:
                f.write(f"| {p['owner']} | {p['repo']} | {p['url']} | {p['last_modified'] or 'N/A'} |\n")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _write_files)

    cost = int((time.time() - t0) * 1000)
    owners = set(p["owner"] for p in sorted_projects)

    return {
        "code": 200,
        "msg": f"索引抓取完成: {len(sorted_projects)} 个项目",
        "data": {
            "total_projects": len(sorted_projects),
            "unique_owners": len(owners),
            "sub_sitemaps": len(sub_sitemaps),
            "failed": failed,
            "files": {
                "csv": str(_INDEX_DIR / "deepwiki_index.csv"),
                "json": str(_INDEX_DIR / "deepwiki_index.json"),
                "md": str(_INDEX_DIR / "INDEX.md"),
            },
            "cost_time": cost,
        }
    }


@cached(ttl=60)
@tool("deepwiki_search", "在已抓取的DeepWiki索引中搜索项目（按owner/repo名称模糊匹配）")
async def deepwiki_search(keyword: str, limit: int = 20) -> dict:
    """搜索DeepWiki索引中的项目

    :param keyword: 搜索关键词（匹配owner或repo名）
    :param limit: 返回结果数量上限
    """
    projects = _load_index()
    if not projects:
        return {"code": 404, "msg": "索引不存在，请先运行 deepwiki_fetch_index", "data": {}}

    keyword_lower = keyword.lower()
    matches = [
        p for p in projects
        if keyword_lower in p["owner"].lower() or keyword_lower in p["repo"].lower()
    ]

    return {
        "code": 200,
        "msg": f"找到 {len(matches)} 个匹配项目",
        "data": {
            "total": len(matches),
            "results": matches[:limit],
        }
    }


@tool("deepwiki_get_stats", "获取DeepWiki索引的统计信息")
@cached(ttl=300)
async def deepwiki_get_stats() -> dict:
    """获取索引统计：项目数、Top作者、最新更新等"""
    projects = _load_index()
    if not projects:
        return {"code": 404, "msg": "索引不存在，请先运行 deepwiki_fetch_index", "data": {}}

    # 统计Top作者（dict计数比重复get更高效）
    owner_count: Dict[str, int] = {}
    for p in projects:
        owner = p["owner"]
        owner_count[owner] = owner_count.get(owner, 0) + 1
    # heapq 取 top-20
    top_owners = heapq.nlargest(20, owner_count.items(), key=lambda x: x[1])

    # 最近更新（heapq 取 top-10，避免全量排序）
    with_date = [p for p in projects if p.get("last_modified")]
    recent = heapq.nlargest(10, with_date, key=lambda x: x["last_modified"])

    return {
        "code": 200,
        "msg": f"共 {len(projects)} 个项目, {len(owner_count)} 个独立作者",
        "data": {
            "total_projects": len(projects),
            "unique_owners": len(owner_count),
            "top_owners": [{"owner": o, "count": c} for o, c in top_owners],
            "recent_updates": recent,
        }
    }
