"""
AI知识库 Web 管理界面 - FastAPI + Jinja2

轻量级Web管理界面，封装KnowledgeBaseManager提供REST API和单页面管理面板。

启动方式:
    python kb_web.py
    # 或
    uvicorn kb_web:app --host 0.0.0.0 --port 8080
"""

import os
import json
import tempfile
import threading
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile, File, Query
from fastapi.responses import HTMLResponse, JSONResponse
from ..utils import _ok, _err
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .kb_core import KnowledgeBaseManager
from .utils import build_graph_from_index
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
VAULT_PATH = os.getenv("KB_VAULT_PATH", str(Path(__file__).resolve().parent / "AI知识库"))
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
UPLOAD_DIR = Path(tempfile.gettempdir()) / "kb_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = UPLOAD_DIR  # 复用临时目录

# ---------------------------------------------------------------------------
# 全局管理器实例（延迟初始化）
# ---------------------------------------------------------------------------
_kb: Optional[KnowledgeBaseManager] = None
_kb_lock = threading.Lock()


def get_kb() -> KnowledgeBaseManager:
    global _kb
    if _kb is not None:
        return _kb
    with _kb_lock:
        if _kb is not None:
            return _kb
        _kb = KnowledgeBaseManager(VAULT_PATH)
    return _kb


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    get_kb()
    yield


app = FastAPI(title="AI知识库管理", version="1.0", lifespan=lifespan)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 模板引擎
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 页面路由
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("kb_dashboard.html", {"request": request})


# ---------------------------------------------------------------------------
# 文档操作 API
# ---------------------------------------------------------------------------
@app.get("/api/documents")
async def api_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="搜索关键词"),
):
    kb = get_kb()
    index = kb._load_index()
    docs = index.get("documents", [])

    # 搜索过滤
    if search:
        words = search.lower().split()
        filtered = []
        for doc in docs:
            text = " ".join([
                doc.get("title", ""),
                " ".join(doc.get("concepts", [])),
                " ".join(doc.get("entities", [])),
                " ".join(doc.get("tags", [])),
                doc.get("summary", ""),
            ]).lower()
            if any(w in text for w in words):
                filtered.append(doc)
        docs = filtered

    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size

    return _ok({
        "total": total,
        "page": page,
        "page_size": page_size,
        "documents": docs[start:end],
    })


@app.get("/api/documents/{doc_id}")
async def api_document_detail(doc_id: str):
    kb = get_kb()
    index = kb._load_index()
    for doc in index.get("documents", []):
        path = doc.get("path", "")
        if path == doc_id or path.rsplit(".", 1)[0] == doc_id:
            # 读取文档内容
            doc_path = kb.vault_path / path
            content = ""
            if doc_path.exists():
                content = doc_path.read_text(encoding="utf-8")
            return _ok({"document": doc, "content": content})
    return _err(404, "document not found")


# ---------------------------------------------------------------------------
# 导入 API
# ---------------------------------------------------------------------------
@app.post("/api/import")
async def api_import_file(file: UploadFile = File(...), category: Optional[str] = None):
    kb = get_kb()
    if not file.filename:
        return JSONResponse({"error": "filename is required"}, status_code=400)
    # 保存上传文件到临时目录
    filename = os.path.basename(file.filename)
    save_path = UPLOAD_DIR / filename
    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        kb.import_document(str(save_path), category=category)
        return _ok(msg=f"imported {file.filename}")
    except Exception as e:
        return _err(500, f"import failed: {e}")
    finally:
        # 清理临时文件
        if save_path.exists():
            save_path.unlink()


@app.post("/api/import-url")
async def api_import_url(request: Request):
    body = await request.json()
    url = body.get("url", "")
    category = body.get("category")

    if not url:
        return _err(400, "url is required")

    kb = get_kb()
    # 通过 curl 下载文件到临时目录
    import subprocess
    tmp_path = DOWNLOAD_DIR / url.split("/")[-1].split("?")[0] or "download.txt"
    try:
        result = subprocess.run(
            ["curl", "-sL", "-o", str(tmp_path), url],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            return _err(500, f"download failed: {result.stderr.decode()}")
        kb.import_document(str(tmp_path), category=category)
        return _ok(msg=f"imported from {url}")
    except Exception as e:
        return _err(500, str(e))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# 搜索 API
# ---------------------------------------------------------------------------
@app.get("/api/search")
async def api_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)):
    kb = get_kb()
    # 使用 unified_search 的逻辑，但不调用 LLM 生成回答
    index = kb._load_index()
    results = []
    if index.get("documents"):
        words = q.lower().split()
        for doc in index["documents"]:
            score = 0
            text = " ".join([
                doc.get("title", ""),
                " ".join(doc.get("concepts", [])),
                " ".join(doc.get("entities", [])),
                " ".join(doc.get("tags", [])),
                doc.get("summary", ""),
            ]).lower()
            for w in words:
                if w in text:
                    score += 1
            if score > 0:
                results.append({"title": doc.get("title", ""), "score": score,
                                "path": doc.get("path", ""), "tags": doc.get("tags", []),
                                "summary": doc.get("summary", "")})
        results.sort(key=lambda x: x["score"], reverse=True)

    return _ok({"results": results[:limit], "total": len(results)})


# ---------------------------------------------------------------------------
# 知识图谱 API
# ---------------------------------------------------------------------------
@app.get("/api/graph")
async def api_graph():
    kb = get_kb()
    index_file = kb.index_dir / "documents.json"
    if not index_file.exists():
        return _ok({"nodes": [], "edges": []})

    with open(index_file, "r", encoding="utf-8") as f:
        index = json.load(f)

    graph = build_graph_from_index(index)
    return _ok(graph)


# ---------------------------------------------------------------------------
# 分类管理 API
# ---------------------------------------------------------------------------
@app.get("/api/categories")
async def api_categories():
    kb = get_kb()
    result = kb.discover_categories()
    return _ok(result)


@app.post("/api/classify")
async def api_classify(request: Request):
    body = await request.json()
    content = body.get("content", "")
    title = body.get("title", "untitled")

    kb = get_kb()
    category = kb.auto_classify(content, title)
    return _ok({"category": category})


@app.post("/api/merge")
async def api_merge(request: Request):
    body = await request.json()
    source = body.get("source", "")
    target = body.get("target", "")

    if not source or not target:
        return _err(400, "source and target are required")

    kb = get_kb()
    kb.merge_categories(source, target)
    return _ok(msg=f"merged '{source}' into '{target}'")


# ---------------------------------------------------------------------------
# 系统状态 API
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def api_status():
    kb = get_kb()
    index = kb._load_index()
    doc_count = len(index.get("documents", []))

    # 缓存状态
    try:
        stats = kb.cache.stats()
        cache_hit = stats.get("hit_rate", "N/A")
    except Exception as e:
        logger.debug("获取缓存统计失败: %s", e)
        cache_hit = "N/A"

    # git 状态
    sync_status = "unknown"
    if kb._is_git_repo():
        r = kb._git_run(["status", "--porcelain"])
        if r.returncode == 0:
            changes = len(r.stdout.strip().splitlines()) if r.stdout.strip() else 0
            sync_status = f"{changes} pending" if changes else "clean"
        else:
            sync_status = "error"
    else:
        sync_status = "not a git repo"

    return _ok({
        "vault_path": str(kb.vault_path),
        "doc_count": doc_count,
        "cache_hit_rate": cache_hit,
        "sync_status": sync_status,
        "categories": list(index.get("concepts", {}).keys())[:10],
    })


@app.get("/api/cache/stats")
async def api_cache_stats():
    kb = get_kb()
    try:
        stats = kb.cache.stats()
        return _ok(stats)
    except Exception as e:
        return _err(500, str(e))


@app.post("/api/cache/clear")
async def api_cache_clear():
    kb = get_kb()
    kb.cache_clear()
    return _ok(msg="cache cleared")


# ---------------------------------------------------------------------------
# 同步与备份 API
# ---------------------------------------------------------------------------
@app.post("/api/sync")
async def api_sync(request: Request):
    try:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    memory_dir = body.get("memory_dir")
    kb = get_kb()
    try:
        if memory_dir:
            kb.sync_memory_to_kb(memory_dir)
        else:
            # 默认同步路径
            default_mem = str(Path.home() / ".claude" / "projects"
                              / "d--Users-lenovo-Desktop-claude-workspace" / "memory")
            kb.sync_memory_to_kb(default_mem)
        return _ok(msg="sync completed")
    except Exception as e:
        return _err(500, f"sync failed: {e}")


@app.post("/api/backup")
async def api_backup(request: Request):
    try:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    except json.JSONDecodeError:
        return _err(400, "invalid JSON in request body")
    message = body.get("message", "")
    kb = get_kb()
    try:
        kb.backup(message)
        return _ok(msg="backup completed")
    except Exception as e:
        return _err(500, f"backup failed: {e}")


@app.get("/api/backup/history")
async def api_backup_history(limit: int = Query(20, ge=1, le=100)):
    kb = get_kb()
    if not kb._is_git_repo():
        return _ok({"history": [], "msg": "not a git repo"})

    r = kb._git_run(["log", f"--max-count={limit}", "--format=%h|%ai|%s"])
    history = []
    if r.returncode == 0 and r.stdout.strip():
        for line in r.stdout.strip().splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                history.append({
                    "hash": parts[0],
                    "date": parts[1].strip(),
                    "message": parts[2],
                })
    return _ok({"history": history})


# ---------------------------------------------------------------------------
# 文档删除 API
# ---------------------------------------------------------------------------
@app.delete("/api/documents/{doc_id:path}")
async def api_delete_document(doc_id: str):
    kb = get_kb()
    index = kb._load_index()
    for i, doc in enumerate(index.get("documents", [])):
        path = doc.get("path", "")
        if path == doc_id or path.rsplit(".", 1)[0] == doc_id:
            # 删除文件
            doc_path = kb.vault_path / doc["path"]
            if doc_path.exists():
                doc_path.unlink()
            # 从索引中移除
            index["documents"].pop(i)
            index_file = kb.index_dir / "documents.json"
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, indent=2, ensure_ascii=False)
            kb.cache.invalidate()
            return _ok(msg=f"deleted {doc.get('title', '')}")
    return _err(404, "document not found")


# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
