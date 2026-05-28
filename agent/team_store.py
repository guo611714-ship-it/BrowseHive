"""Agent Team 消息总线与 TeamStore"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class MessageBus:
    """基于文件 inbox 的消息总线"""

    def __init__(self, team_dir: Path):
        self.team_dir = Path(team_dir)
        self.inbox_dir = self.team_dir / "inbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, to: str, message: Dict[str, Any], wake: bool = False) -> str:
        """发送消息到队友 inbox"""
        msg_id = f"msg_{int(datetime.now().timestamp() * 1000)}"

        envelope = {
            "id": msg_id,
            "timestamp": datetime.now().isoformat(),
            "to": to,
            "wake": wake,
            **message
        }

        inbox_file = self.inbox_dir / f"{to}.jsonl"
        with open(inbox_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(envelope, ensure_ascii=False) + "\n")

        return msg_id

    def read(self, actor: str, clear: bool = True) -> List[Dict]:
        """读取 actor 的 inbox"""
        inbox_file = self.inbox_dir / f"{actor}.jsonl"
        if not inbox_file.exists():
            return []

        messages = []
        with open(inbox_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    messages.append(json.loads(line))

        if clear:
            inbox_file.unlink(missing_ok=True)

        return messages

    def broadcast(self, to: List[str], message: Dict[str, Any]) -> List[str]:
        """广播消息到多个队友"""
        msg_ids = []
        for name in to:
            msg_id = self.send(name, message)
            msg_ids.append(msg_id)
        return msg_ids


class TeamStore:
    """团队状态持久化管理"""

    def __init__(self, team_dir: Path):
        self.team_dir = Path(team_dir)
        self.config_file = self.team_dir / "config.json"
        self.inbox_dir = self.team_dir / "inbox"
        self.threads_dir = self.team_dir / "threads"
        self.checkpoints_dir = self.team_dir / "checkpoints"
        self.cursors_dir = self.team_dir / "cursors"

        # 确保目录存在
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.threads_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.cursors_dir.mkdir(parents=True, exist_ok=True)

        self._config = self._load_config()

    def _load_config(self) -> Dict:
        """加载团队配置"""
        if not self.config_file.exists():
            return {"teammates": []}
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # 备份损坏文件并返回空配置
            backup = self.config_file.with_suffix(".json.corrupt")
            try:
                self.config_file.rename(backup)
            except Exception:
                pass
            return {"teammates": []}

    @property
    def teammates(self) -> List[Dict]:
        """获取所有队友配置"""
        return self._config.get("teammates", [])

    def get_teammate(self, name: str) -> Optional[Dict]:
        """获取指定队友配置"""
        for tm in self.teammates:
            if tm["name"] == name:
                return tm
        return None

    def update_status(self, name: str, status: str) -> bool:
        """更新队友状态"""
        tm = self.get_teammate(name)
        if not tm:
            return False
        tm["status"] = status
        self._save_config()
        return True

    def add_teammate(self, name: str, role: str, agent_type: str, description: str = "",
                     max_turns: int = 50, model_role: str = "main") -> bool:
        """添加新队友"""
        if self.get_teammate(name):
            return False  # 已存在

        new_tm = {
            "name": name,
            "role": role,
            "agent_type": agent_type,
            "status": "idle",
            "description": description,
            "max_turns": max_turns,
            "model_role": model_role,
            "created_at": datetime.now().isoformat()
        }

        self.teammates.append(new_tm)
        self._save_config()

        # 创建 inbox 文件
        inbox_file = self.inbox_dir / f"{name}.jsonl"
        inbox_file.touch(exist_ok=True)

        return True

    def remove_teammate(self, name: str) -> bool:
        """移除队友"""
        tm = self.get_teammate(name)
        if not tm:
            return False

        self._config["teammates"] = [t for t in self.teammates if t["name"] != name]
        self._save_config()

        # 清理 inbox 文件
        inbox_file = self.inbox_dir / f"{name}.jsonl"
        if inbox_file.exists():
            inbox_file.unlink()

        return True

    def _save_config(self):
        """保存配置到文件"""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    def get_thread(self, name: str) -> List[Dict]:
        """获取队友的独立上下文线程"""
        thread_file = self.threads_dir / f"{name}.json"
        if not thread_file.exists():
            return []
        try:
            with open(thread_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

    def save_thread(self, name: str, thread: List[Dict]):
        """保存队友的独立上下文线程"""
        thread_file = self.threads_dir / f"{name}.json"
        with open(thread_file, "w", encoding="utf-8") as f:
            json.dump(thread, f, indent=2, ensure_ascii=False)

    def get_checkpoint(self, name: str) -> Optional[Dict]:
        """获取队友的检查点"""
        checkpoint_file = self.checkpoints_dir / f"{name}.json"
        if not checkpoint_file.exists():
            return None
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None

    def save_checkpoint(self, name: str, checkpoint: Dict):
        """保存队友的检查点"""
        checkpoint_file = self.checkpoints_dir / f"{name}.json"
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2, ensure_ascii=False)

    def clear_checkpoint(self, name: str):
        """清除队友的检查点（任务完成后）"""
        checkpoint_file = self.checkpoints_dir / f"{name}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

    def get_cursor(self, actor: str) -> int:
        """获取 inbox 已读游标"""
        cursor_file = self.cursors_dir / f"{actor}.txt"
        if not cursor_file.exists():
            return 0
        try:
            return int(cursor_file.read_text().strip())
        except:
            return 0

    def set_cursor(self, actor: str, position: int):
        """设置 inbox 已读游标"""
        cursor_file = self.cursors_dir / f"{actor}.txt"
        cursor_file.write_text(str(position))

    def reset(self):
        """重置整个团队（清空所有状态）"""
        # 清空 threads
        for f in self.threads_dir.glob("*.json"):
            f.unlink()
        # 清空 checkpoints
        for f in self.checkpoints_dir.glob("*.json"):
            f.unlink()
        # 清空 cursors
        for f in self.cursors_dir.glob("*.txt"):
            f.unlink()
        # 清空 inbox
        for f in self.inbox_dir.glob("*.jsonl"):
            f.unlink()
            # 创建空文件
            f.touch()


# 全局便利函数
def get_team_store() -> TeamStore:
    """获取 TeamStore 实例"""
    team_dir = Path(".team")
    return TeamStore(team_dir)

def get_message_bus() -> MessageBus:
    """获取 MessageBus 实例"""
    team_dir = Path(".team")
    return MessageBus(team_dir)
