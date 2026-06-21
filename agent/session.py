"""会话持久化与恢复"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class SessionManager:
    """会话管理器 - 支持保存、加载、恢复"""

    def __init__(self, sessions_dir: Path = None):
        self.sessions_dir = sessions_dir or Path(".team/sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session_id: str, state: Dict[str, Any]) -> Path:
        """保存会话状态"""
        session_path = self.sessions_dir / f"{session_id}.json"
        temp_path = session_path.with_suffix(".tmp")

        state["_saved_at"] = datetime.now().isoformat()
        state["_session_id"] = session_id

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        os.replace(str(temp_path), str(session_path))
        return session_path

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """加载会话状态"""
        session_path = self.sessions_dir / f"{session_id}.json"
        if not session_path.exists():
            return None

        try:
            with open(session_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话"""
        sessions = []
        for path in self.sessions_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "id": data.get("_session_id", path.stem),
                    "saved_at": data.get("_saved_at"),
                    "path": str(path)
                })
            except Exception as e:
                logger.debug("caught exception, continuing: %s", e)
                continue
        return sorted(sessions, key=lambda x: x.get("saved_at", ""), reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        session_path = self.sessions_dir / f"{session_id}.json"
        if session_path.exists():
            session_path.unlink()
            return True
        return False

    def export_session(self, session_id: str, export_path: Path) -> bool:
        """导出会话"""
        data = self.load_session(session_id)
        if data is None:
            return False
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True

    def import_session(self, import_path: Path, session_id: str = None) -> Optional[str]:
        """导入会话"""
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.debug("caught exception: %s", e)
            return None

        sid = session_id or data.get("_session_id", import_path.stem)
        self.save_session(sid, data)
        return sid
