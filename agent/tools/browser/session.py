"""浏览器工具 — 会话管理"""

import json
import time
import uuid
import logging
from typing import Dict
from pathlib import Path

from ..tool_registry import tool
from ...config import BROWSER_SESSIONS_DIR
from ..checkpoint import BrowserCheckpoint
from . import utils

logger = logging.getLogger(__name__)

# 会话内存存储路径
_SESSION_MEMORY_DIR = BROWSER_SESSIONS_DIR


@tool("start_browser_session", "开始新的浏览器会话，创建检查点和独立记忆")
def start_browser_session(task: str = "") -> str:
    """开始新的浏览器会话，创建检查点和独立记忆"""
    session_id = f"browser_{uuid.uuid4().hex[:8]}"
    utils._current_checkpoint = BrowserCheckpoint(session_id=session_id, task=task)
    utils._checkpoint_mgr.save(utils._current_checkpoint)

    # 创建独立记忆空间
    _SESSION_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    utils._session_memories[session_id] = {
        "session_id": session_id,
        "task": task,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "visited_urls": [],
        "actions": [],
        "results": [],
        "context": {}  # 存储cookie/会话状态等
    }

    logger.info(f"浏览器会话启动: {session_id}")
    return session_id


@tool("end_browser_session", "结束浏览器会话，保存检查点和记忆")
def end_browser_session(session_id: str = None) -> Dict:
    """结束浏览器会话，保存检查点和记忆"""
    if utils._current_checkpoint:
        utils._current_checkpoint.status = "completed"
        utils._checkpoint_mgr.save(utils._current_checkpoint)
        session_id = session_id or utils._current_checkpoint.session_id
        utils._current_checkpoint = None
    elif session_id:
        utils._current_checkpoint = None

    # 保存记忆到磁盘
    if session_id and session_id in utils._session_memories:
        memory = utils._session_memories[session_id]
        memory["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        memory_file = _SESSION_MEMORY_DIR / f"{session_id}.json"
        memory_file.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
        result = {"session_id": session_id, "operations": len(memory["actions"])}
        del utils._session_memories[session_id]
        return result

    return {"session_id": session_id, "operations": 0}


@tool("get_session_memory", "获取浏览器会话记忆")
def get_session_memory(session_id: str) -> Dict:
    """获取会话记忆"""
    # 先检查内存
    if session_id in utils._session_memories:
        return utils._session_memories[session_id]
    # 再检查磁盘
    memory_file = _SESSION_MEMORY_DIR / f"{session_id}.json"
    if memory_file.exists():
        return json.loads(memory_file.read_text(encoding="utf-8"))
    return {}


def _record_to_session(tool_name: str, args: Dict, result: Dict):
    """记录操作到当前会话的独立记忆"""
    if utils._current_checkpoint and utils._current_checkpoint.session_id in utils._session_memories:
        mem = utils._session_memories[utils._current_checkpoint.session_id]
        mem["actions"].append({
            "tool": tool_name, "args": str(args)[:200],
            "result_code": result.get("code"), "time": time.strftime("%H:%M:%S")
        })
        # 记录URL访问
        if tool_name == "navigate" and "url" in args:
            mem["visited_urls"].append(args["url"])
        # 记录关键结果
        if result.get("code", 0) < 300 and result.get("data"):
            mem["results"].append({
                "tool": tool_name, "data_summary": str(result["data"])[:300]
            })
