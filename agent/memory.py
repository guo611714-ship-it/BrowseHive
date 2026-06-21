"""三层记忆系统：工作记忆、情景记忆、长期记忆"""

import glob
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Truncation thresholds
HISTORY_MAX_SIZE = 10 * 1024 * 1024  # 10MB
TOKENS_MAX_SIZE = 5 * 1024 * 1024    # 5MB
TOKEN_AGE_DAYS = 30                   # archive token records older than 30 days
ARCHIVE_RETENTION_DAYS = 90           # delete archive files older than 90 days


class MemoryStore:
    """记忆存储管理器（线程安全）"""

    def __init__(self, memory_dir: Path = Path("memory")):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._history_lock = threading.RLock()
        self._compress_lock = threading.Lock()

        self.long_term_file = self.memory_dir / "MEMORY.md"
        self.user_file = self.memory_dir / "USER.md"
        self.history_file = self.memory_dir / "history.jsonl"
        self.tokens_file = self.memory_dir / "tokens.jsonl"

        # 初始化文件
        self._ensure()

    # -- 公开锁接口（供 AgentLoop 等外部调用者使用）--

    def try_compress_lock(self) -> bool:
        """尝试获取压缩锁，已被持有时返回 False"""
        return self._compress_lock.acquire(blocking=False)

    def release_compress_lock(self):
        """释放压缩锁"""
        self._compress_lock.release()

    @contextmanager
    def compress_context(self):
        """压缩操作的上下文管理器，自动获取/释放两把锁"""
        with self._compress_lock:
            with self._history_lock:
                yield

    def _ensure(self):
        """确保必要文件存在"""
        # 长期记忆
        if not self.long_term_file.exists():
            self.long_term_file.write_text(
                "# 长期记忆\n\n暂无内容，将在压缩时自动生成。\n",
                encoding="utf-8"
            )

        # 用户偏好
        if not self.user_file.exists():
            self.user_file.write_text(
                "# 用户偏好\n\n暂无个性化设置。\n",
                encoding="utf-8"
            )

        # 历史日志
        self.history_file.touch(exist_ok=True)
        self.tokens_file.touch(exist_ok=True)

    @property
    def _archive_dir(self) -> Path:
        """Archive directory, created lazily"""
        d = self.memory_dir / "archive"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _archive_and_truncate_history(self):
        """Archive the older half of history.jsonl. Caller must hold _history_lock."""
        try:
            lines = self.history_file.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            return
        if not lines:
            return

        split = len(lines) // 2
        if split == 0:
            return

        archived = lines[:split]
        kept = lines[split:]

        # Write archived portion
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = self._archive_dir / f"history_{ts}.jsonl"
        with open(archive_path, "w", encoding="utf-8") as f:
            f.writelines(archived)

        # Rewrite main file with recent half
        self.history_file.write_text("".join(kept), encoding="utf-8")

        self._cleanup_old_archives()

    def _archive_old_token_records(self):
        """Remove token records older than TOKEN_AGE_DAYS from tokens.jsonl and archive them.
        Caller must hold _history_lock."""
        try:
            lines = self.tokens_file.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            return
        if not lines:
            return

        cutoff = time.time() - TOKEN_AGE_DAYS * 86400
        old_lines = []
        kept_lines = []

        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line.strip())
                ts = datetime.fromisoformat(record["timestamp"]).timestamp()
                if ts < cutoff:
                    old_lines.append(line)
                else:
                    kept_lines.append(line)
            except (json.JSONDecodeError, KeyError, ValueError):
                kept_lines.append(line)

        if not old_lines:
            return

        # Archive old records
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = self._archive_dir / f"tokens_{ts}.jsonl"
        with open(archive_path, "w", encoding="utf-8") as f:
            f.writelines(old_lines)

        # Rewrite main file with recent records
        self.tokens_file.write_text("".join(kept_lines), encoding="utf-8")

        self._cleanup_old_archives()

    def _cleanup_old_archives(self):
        """Remove archive files older than ARCHIVE_RETENTION_DAYS."""
        try:
            cutoff = time.time() - ARCHIVE_RETENTION_DAYS * 86400
            for pattern in ("history_*.jsonl", "tokens_*.jsonl"):
                for fpath in glob.glob(str(self._archive_dir / pattern)):
                    try:
                        if os.path.getmtime(fpath) < cutoff:
                            os.remove(fpath)
                    except OSError:
                        pass
        except OSError:
            pass

    def _cleanup_old_versions(self, subdir: str, keep: int = 10):
        """Remove old version snapshots, keeping the most recent *keep* files."""
        try:
            snapshot_dir = self.memory_dir / "versions" / subdir
            if not snapshot_dir.is_dir():
                return
            snapshots = sorted(snapshot_dir.glob("*.snapshot.md"), key=lambda p: p.name)
            for old in snapshots[:-keep]:
                try:
                    old.unlink()
                except OSError:
                    pass
        except OSError:
            pass

    def append_history(self, message: Dict[str, Any]):
        """追加一条对话历史（线程安全）"""
        with self._history_lock:
            # Truncate if file exceeds size threshold
            if self.history_file.exists() and self.history_file.stat().st_size > HISTORY_MAX_SIZE:
                self._archive_and_truncate_history()

            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def get_recent_history(self, limit: int = 200) -> List[Dict]:
        """获取最近的历史记录"""
        with self._history_lock:
            if not self.history_file.exists():
                return []

            with open(self.history_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            start = max(0, len(lines) - limit)
            recent = [json.loads(line.strip()) for line in lines[start:] if line.strip()]
            return recent

    def clear_history(self):
        """清空热历史（压缩后调用）"""
        with self._history_lock:
            self.history_file.write_text("", encoding="utf-8")

    def get_long_term_memory(self) -> str:
        """读取长期记忆"""
        return self.long_term_file.read_text(encoding="utf-8")

    def update_long_term_memory(self, content: str):
        """更新长期记忆（带版本快照）"""
        # 创建版本快照
        snapshot_dir = self.memory_dir / "versions" / "long_term"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        snapshot_file = snapshot_dir / f"{timestamp}.snapshot.md"

        if self.long_term_file.exists():
            snapshot_file.write_text(self.long_term_file.read_text(encoding="utf-8"), encoding="utf-8")

        # 写入新版本
        self.long_term_file.write_text(content, encoding="utf-8")

        self._cleanup_old_versions("long_term")

    def get_user_prefs(self) -> str:
        """读取用户偏好"""
        return self.user_file.read_text(encoding="utf-8")

    def update_user_prefs(self, content: str):
        """更新用户偏好（带版本快照）"""
        snapshot_dir = self.memory_dir / "versions" / "user"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        snapshot_file = snapshot_dir / f"{timestamp}.snapshot.md"

        if self.user_file.exists():
            snapshot_file.write_text(self.user_file.read_text(encoding="utf-8"), encoding="utf-8")

        self.user_file.write_text(content, encoding="utf-8")

        self._cleanup_old_versions("user")

    def append_daily_memory(self, content: str):
        """追加今日情景记忆"""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = self.memory_dir / f"{today}.md"
        if not daily_file.exists():
            daily_file.write_text(f"# {today} 情景记忆\n\n", encoding="utf-8")

        with open(daily_file, "a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.now().strftime('%H:%M:%S')}\n\n{content}\n")

    def record_token_usage(self, provider: str, model: str, input_tokens: int,
                          output_tokens: int, cache_read: int = 0, cache_create: int = 0,
                          usage_type: str = "main_agent", model_role: str = "main",
                          route_reason: str = None):
        """记录 token 使用情况"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "input": input_tokens,
            "output": output_tokens,
            "cache_read": cache_read,
            "cache_create": cache_create,
            "usage_type": usage_type,
            "model_role": model_role
        }
        if route_reason:
            record["route_reason"] = route_reason

        with self._history_lock:
            # Truncate if file exceeds size threshold
            if self.tokens_file.exists() and self.tokens_file.stat().st_size > TOKENS_MAX_SIZE:
                self._archive_old_token_records()

            with open(self.tokens_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_token_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取 token 统计"""
        if not self.tokens_file.exists():
            return {}

        stats = {
            "total_input": 0,
            "total_output": 0,
            "total_cache_read": 0,
            "total_cache_create": 0,
            "by_model": {},
            "by_usage_type": {}
        }

        cutoff = datetime.now().timestamp() - days * 24 * 3600

        with open(self.tokens_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    ts = datetime.fromisoformat(record["timestamp"]).timestamp()
                    if ts < cutoff:
                        continue

                    # 总计
                    stats["total_input"] += record["input"]
                    stats["total_output"] += record["output"]
                    stats["total_cache_read"] += record.get("cache_read", 0)
                    stats["total_cache_create"] += record.get("cache_create", 0)

                    # 按模型
                    model_key = f"{record['provider']}/{record['model']}"
                    if model_key not in stats["by_model"]:
                        stats["by_model"][model_key] = {
                            "input": 0,
                            "output": 0,
                            "count": 0
                        }
                    stats["by_model"][model_key]["input"] += record["input"]
                    stats["by_model"][model_key]["output"] += record["output"]
                    stats["by_model"][model_key]["count"] += 1

                    # 按使用类型
                    usage = record["usage_type"]
                    if usage not in stats["by_usage_type"]:
                        stats["by_usage_type"][usage] = {
                            "input": 0,
                            "output": 0,
                            "count": 0
                        }
                    stats["by_usage_type"][usage]["input"] += record["input"]
                    stats["by_usage_type"][usage]["output"] += record["output"]
                    stats["by_usage_type"][usage]["count"] += 1

                except json.JSONDecodeError:
                    continue

        return stats
