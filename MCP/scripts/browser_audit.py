"""浏览器操作审计日志 — 记录每一步操作的时间、截图、DOM状态和返回结果"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List


class BrowserAuditLog:
    """浏览器操作审计日志记录器"""

    def __init__(self, log_dir: str = ".team/browser_audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_session: Optional[str] = None
        self._entries: List[Dict] = []

    def start_session(self, task_id: str) -> str:
        """开始新的审计会话"""
        self._current_session = task_id
        self._entries = []
        return task_id

    def log_step(self, step_name: str, action: str, params: Dict = None,
                 result: Dict = None, screenshot_path: str = None,
                 dom_summary: str = None) -> Dict:
        """记录一个操作步骤"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_ms": round(time.time() * 1000),
            "session": self._current_session,
            "step": step_name,
            "action": action,
            "params": params or {},
            "result": result,
            "screenshot": screenshot_path,
            "dom_summary": dom_summary,
            "success": result.get("ok", False) if result else None,
        }
        self._entries.append(entry)
        return entry

    def end_session(self) -> Dict:
        """结束会话并保存日志"""
        if not self._current_session:
            return {"error": "no active session"}

        summary = {
            "session": self._current_session,
            "total_steps": len(self._entries),
            "successful": sum(1 for e in self._entries if e.get("success")),
            "failed": sum(1 for e in self._entries if e.get("success") is False),
            "duration_ms": (
                self._entries[-1]["elapsed_ms"] - self._entries[0]["elapsed_ms"]
                if self._entries else 0
            ),
            "entries": self._entries,
        }

        filename = f"{self._current_session}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.log_dir / filename
        filepath.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        session = self._current_session
        self._current_session = None
        self._entries = []
        return {"session": session, "log_file": str(filepath), **summary}

    def get_recent(self, n: int = 10) -> List[Dict]:
        """获取最近 n 条日志"""
        return self._entries[-n:] if self._entries else []


_audit_log = None


def get_browser_audit_log() -> BrowserAuditLog:
    global _audit_log
    if _audit_log is None:
        _audit_log = BrowserAuditLog()
    return _audit_log
