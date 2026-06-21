"""Agent Team 集中存储 — 工作区外的记忆和状态文件"""

import json
import os
import threading
from pathlib import Path

# 存储根目录: ~/.agent-team/store/
STORE_DIR = Path.home() / ".agent-team" / "store"
INDEX_PATH = STORE_DIR / "index.json"

_lock = threading.Lock()


def _safe_name(name: str) -> Path:
    """校验文件名，防止路径穿越"""
    name = name.replace("\\", "/").lstrip("/")
    if ".." in name.split("/"):
        raise ValueError(f"非法路径: {name}")
    return STORE_DIR / name


def ensure_store():
    """确保存储目录存在"""
    STORE_DIR.mkdir(parents=True, exist_ok=True)


def save(name: str, data):
    """保存数据到存储文件（原子写入）"""
    ensure_store()
    path = _safe_name(name)
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        if isinstance(data, (dict, list)):
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif isinstance(data, str):
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(data)
        else:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        _update_index(name, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return path


def load(name: str, default=None):
    """加载存储文件"""
    try:
        path = _safe_name(name)
    except ValueError:
        return default
    if not path.exists():
        return default
    try:
        if path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        return default


def remove(name: str):
    """删除存储文件"""
    try:
        path = _safe_name(name)
    except ValueError:
        return
    if path.exists():
        path.unlink()
    _remove_index(name)


def list_files():
    """列出所有存储文件"""
    ensure_store()
    return [f.name for f in STORE_DIR.iterdir() if f.is_file()]


def get_index():
    """获取存储索引"""
    return load("index.json", default={"files": {}})


def _update_index(name: str, path: Path):
    """更新索引（原子写入）"""
    with _lock:
        index = get_index()
        index["files"][name] = {
            "size": path.stat().st_size if path.exists() else 0,
            "type": _guess_type(name),
        }
        tmp = INDEX_PATH.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
            os.replace(tmp, INDEX_PATH)
        except Exception:
            if tmp.exists():
                tmp.unlink()


def _remove_index(name: str):
    """从索引中移除（原子写入）"""
    with _lock:
        index = get_index()
        index["files"].pop(name, None)
        tmp = INDEX_PATH.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
            os.replace(tmp, INDEX_PATH)
        except Exception:
            if tmp.exists():
                tmp.unlink()


def _guess_type(name: str) -> str:
    """根据文件名猜测类型"""
    if "token" in name:
        return "stats"
    if "history" in name:
        return "conversation"
    if name.endswith(".md"):
        return "document"
    return "data"
