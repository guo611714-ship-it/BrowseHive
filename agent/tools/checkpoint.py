"""检查点恢复系统 — 浏览器操作自动写检查点，崩溃后可断点续跑"""

import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from ..config import CHECKPOINTS_DIR

logger = logging.getLogger(__name__)

_CHECKPOINT_DIR = CHECKPOINTS_DIR


@dataclass
class BrowserCheckpoint:
    """浏览器操作检查点"""
    session_id: str
    task: str
    status: str = "running"  # running | completed | failed | paused
    current_url: str = ""
    steps_completed: List[Dict[str, Any]] = field(default_factory=list)
    steps_remaining: List[Dict[str, Any]] = field(default_factory=list)
    browser_state: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))


class CheckpointManager:
    """检查点管理器"""

    def __init__(self, checkpoint_dir: str = None):
        self.dir = Path(checkpoint_dir) if checkpoint_dir else _CHECKPOINT_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_session_id(session_id: str) -> str:
        """清理session_id，防止路径穿越"""
        import re
        return re.sub(r'[^a-zA-Z0-9_\-]', '', session_id)

    def save(self, checkpoint: BrowserCheckpoint) -> str:
        """保存检查点，返回文件路径"""
        checkpoint.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        safe_id = self._safe_session_id(checkpoint.session_id)
        filepath = self.dir / f"{safe_id}.json"
        filepath.write_text(json.dumps(asdict(checkpoint), ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"检查点已保存: {filepath.name}")
        return str(filepath)

    def load(self, session_id: str) -> Optional[BrowserCheckpoint]:
        """加载检查点"""
        safe_id = self._safe_session_id(session_id)
        filepath = self.dir / f"{safe_id}.json"
        if not filepath.exists():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return BrowserCheckpoint(**data)
        except Exception as e:
            logger.error(f"检查点加载失败: {e}")
            return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有检查点"""
        sessions = []
        for f in self.dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append({
                    "session_id": data.get("session_id"),
                    "task": data.get("task", "")[:50],
                    "status": data.get("status"),
                    "steps_done": len(data.get("steps_completed", [])),
                    "updated_at": data.get("updated_at")
                })
            except Exception as e:
                logger.debug("caught exception, continuing: %s", e)
                continue
        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)

    def delete(self, session_id: str) -> bool:
        """删除检查点"""
        safe_id = self._safe_session_id(session_id)
        filepath = self.dir / f"{safe_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def record_step(self, checkpoint: BrowserCheckpoint, tool_name: str,
                    args: Dict, result: Dict) -> BrowserCheckpoint:
        """记录一个操作步骤（不覆盖已完成状态）"""
        step = {
            "tool": tool_name,
            "args": args,
            "result_code": result.get("code", 0),
            "result_msg": result.get("msg", ""),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        checkpoint.steps_completed.append(step)
        # 只有在未完成状态下才根据结果码设置failed
        if checkpoint.status != "completed" and result.get("code", 0) >= 300:
            checkpoint.status = "failed"
            checkpoint.error = result.get("msg", "操作失败")
        return checkpoint


# 全局单例
_checkpoint_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> CheckpointManager:
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager()
    return _checkpoint_manager
