"""Agent Team 消息总线与 TeamStore"""

import json
import os
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

try:
    import msvcrt
    def _lock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    def _unlock_file(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
except ImportError:
    # Non-Windows: use fcntl (Linux/macOS)
    try:
        import fcntl
        def _lock_file(f):
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        def _unlock_file(f):
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except ImportError:
        # Fallback: no-op (single-process usage)
        def _lock_file(f):
            pass
        def _unlock_file(f):
            pass


class MessageBus:
    """消息总线 — 内存队列优先，文件IPC回退"""

    def __init__(self, team_dir: Path, use_memory: bool = True, max_inbox_size: int = 1000):
        self.team_dir = Path(team_dir)
        self.inbox_dir = self.team_dir / "inbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

        # 内存队列模式（单进程首选，无竞态）
        self._use_memory = use_memory
        self._memory_inbox: Dict[str, List[Dict]] = defaultdict(list)
        self._memory_lock = threading.Lock()

        # 内存队列上限保护
        self._max_inbox_size = max_inbox_size
        self._total_messages: int = 0

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

        if self._use_memory:
            with self._memory_lock:
                self._memory_inbox[to].append(envelope)
                self._total_messages += 1

                # 内存队列上限保护：达到上限时将最旧的消息溢出到磁盘
                if self._total_messages >= self._max_inbox_size:
                    self._overflow_to_disk()
        else:
            inbox_file = self.inbox_dir / f"{to}.jsonl"
            with open(inbox_file, "a", encoding="utf-8") as f:
                _lock_file(f)
                try:
                    f.write(json.dumps(envelope, ensure_ascii=False) + "\n")
                finally:
                    _unlock_file(f)

        return msg_id

    def read(self, actor: str, clear: bool = True) -> List[Dict]:
        """读取 actor 的 inbox"""
        if self._use_memory:
            with self._memory_lock:
                messages = list(self._memory_inbox.get(actor, []))
                if clear:
                    self._memory_inbox[actor] = []

            # 补充溢出到磁盘的消息（先进先出）
            overflow_file = self.inbox_dir / f"{actor}_overflow.jsonl"
            if overflow_file.exists():
                overflow_messages = []
                try:
                    with open(overflow_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                overflow_messages.append(json.loads(line))
                except Exception as e:
                    logger.debug("caught exception: %s", e)

                # 如果清空，删除溢出文件；消息合并返回
                if clear:
                    overflow_file.unlink(missing_ok=True)
                messages = overflow_messages + messages

            return messages

        # 文件模式回退
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

    def get_unread_count(self, actor: str) -> int:
        """获取未读消息数"""
        if self._use_memory:
            with self._memory_lock:
                return len(self._memory_inbox.get(actor, []))

        inbox_file = self.inbox_dir / f"{actor}.jsonl"
        if not inbox_file.exists():
            return 0
        try:
            with open(inbox_file, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception as e:
            logger.debug("caught exception: %s", e)
            return 0

    def _overflow_to_disk(self):
        """将内存中最旧的消息溢出到磁盘（调用时需持有 _memory_lock）"""
        overflow_count = 0
        for actor_name, messages in self._memory_inbox.items():
            if not messages:
                continue

            # 每个 actor 最多溢出一半消息
            overflow_batch_size = max(1, len(messages) // 2)
            overflow_batch = messages[:overflow_batch_size]
            remaining = messages[overflow_batch_size:]

            # 写入溢出文件
            overflow_file = self.inbox_dir / f"{actor_name}_overflow.jsonl"
            try:
                with open(overflow_file, "a", encoding="utf-8") as f:
                    for msg in overflow_batch:
                        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                        overflow_count += 1
            except Exception as e:
                logger.debug("caught exception: %s", e)

            # 更新内存队列
            self._memory_inbox[actor_name] = remaining

        # 更新总消息计数
        self._total_messages = max(0, self._total_messages - overflow_count)

    def get_queue_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        stats = {
            "max_inbox_size": self._max_inbox_size,
            "use_memory": self._use_memory,
            "overflow_files": []
        }

        if self._use_memory:
            with self._memory_lock:
                stats["total_messages"] = self._total_messages
                stats["queue_count"] = len(self._memory_inbox)
                stats["queue_sizes"] = {
                    name: len(msgs) for name, msgs in self._memory_inbox.items()
                }

            # 统计溢出文件（处理并发溢出导致文件被删除的竞态）
            for overflow_file in self.inbox_dir.glob("*_overflow.jsonl"):
                try:
                    with open(overflow_file, "r", encoding="utf-8") as f:
                        line_count = sum(1 for _ in f)
                    stats["overflow_files"].append({
                        "file": overflow_file.name,
                        "messages": line_count
                    })
                except FileNotFoundError:
                    stats["overflow_files"].append({
                        "file": overflow_file.name,
                        "messages": 0
                    })
        else:
            # 文件模式统计
            inbox_files = list(self.inbox_dir.glob("*.jsonl"))
            stats["queue_count"] = len(inbox_files)
            stats["queue_sizes"] = {}
            for f in inbox_files:
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        stats["queue_sizes"][f.stem] = sum(1 for _ in fh)
                except Exception as e:
                    logger.debug("读取队列文件失败: %s", e)
                    stats["queue_sizes"][f.stem] = 0

        return stats


class TeamStore:
    """团队状态持久化管理"""

    def __init__(self, team_dir: Path):
        self.team_dir = Path(team_dir)
        self.config_file = self.team_dir / "config.json"
        self.inbox_dir = self.team_dir / "inbox"
        self.threads_dir = self.team_dir / "threads"
        self.checkpoints_dir = self.team_dir / "checkpoints"
        self.cursors_dir = self.team_dir / "cursors"
        self._config_lock = threading.Lock()

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
            except Exception as e:
                logger.debug("caught exception: %s", e)
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
        """保存配置到文件（线程安全）"""
        with self._config_lock:
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
        except (ValueError, OSError):
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


# 全局单例
_team_store_instance = None
_message_bus_instance = None
_singleton_lock = threading.Lock()


def get_team_store(team_dir: Path = None) -> TeamStore:
    """获取 TeamStore 单例"""
    global _team_store_instance
    if _team_store_instance is not None:
        return _team_store_instance
    with _singleton_lock:
        if _team_store_instance is not None:
            return _team_store_instance
        _team_store_instance = TeamStore(team_dir or Path(".team"))
    return _team_store_instance

def get_message_bus(team_dir: Path = None) -> MessageBus:
    """获取 MessageBus 单例"""
    global _message_bus_instance
    if _message_bus_instance is not None:
        return _message_bus_instance
    with _singleton_lock:
        if _message_bus_instance is not None:
            return _message_bus_instance
        _message_bus_instance = MessageBus(team_dir or Path(".team"))
    return _message_bus_instance


def reset_singletons():
    """重置所有单例（仅用于测试）"""
    global _team_store_instance, _message_bus_instance
    _team_store_instance = None
    _message_bus_instance = None
