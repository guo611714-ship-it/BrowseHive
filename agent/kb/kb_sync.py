#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KB Sync Daemon - 自动文件系统监听 + 增量同步

监听 Obsidian vault 目录变化，自动更新索引。
支持 start / stop / status 命令。

依赖: pip install watchdog
"""

import os
import sys
import json
import time
import signal
import subprocess
import threading
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # 提供空基类以便模块在无watchdog时仍可导入
    class FileSystemEventHandler:
        pass


class KBFileHandler(FileSystemEventHandler):
    """监听文件变化，debounce 后触发同步"""

    def __init__(self, vault_path: Path, debounce_sec: float = 5.0):
        self.vault_path = Path(vault_path)
        self.debounce_sec = debounce_sec
        self._pending: set = set()
        self._timer = None
        self._log_dir = self.vault_path.parent / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _log(self, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        log_file = self._log_dir / "sync.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)

    def _on_change(self):
        """debounce 回调：执行增量同步"""
        changed = list(self._pending)
        self._pending.clear()
        if not changed:
            return

        self._log(f"[SYNC] 检测到 {len(changed)} 个文件变化，开始同步...")
        try:
            self._sync_index()
            self._log("[SYNC] 索引同步完成")
        except Exception as e:
            self._log(f"[ERR] 同步失败: {e}")

    def _sync_index(self):
        """增量同步：扫描 01-Import/ 更新 03-Index/documents.json"""
        import_dir = self.vault_path / "01-Import"
        index_dir = self.vault_path / "03-Index"
        index_file = index_dir / "documents.json"

        index_dir.mkdir(parents=True, exist_ok=True)

        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
        else:
            index = {"documents": [], "concepts": {}, "entities": {}}

        indexed_paths = {doc.get("path") for doc in index.get("documents", [])}

        current_files = set()
        if import_dir.exists():
            for md_file in import_dir.glob("*.md"):
                rel_path = str(md_file.relative_to(self.vault_path))
                current_files.add(rel_path)

                if rel_path not in indexed_paths:
                    try:
                        content = md_file.read_text(encoding="utf-8")
                        title = md_file.stem
                        for line in content.split("\n"):
                            if line.startswith("# ") and not line.startswith("## "):
                                title = line[2:].strip()
                                break

                        doc_record = {
                            "path": rel_path,
                            "title": title,
                            "entities": [],
                            "concepts": [],
                            "tags": [],
                            "created": datetime.now().isoformat(),
                        }
                        index["documents"].append(doc_record)
                    except Exception as e:
                        logger.debug("caught exception: %s", e)

        index["documents"] = [
            doc for doc in index.get("documents", [])
            if doc.get("path") in current_files
        ]

        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def _schedule_sync(self):
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self.debounce_sec, self._on_change)
        self._timer.daemon = True
        self._timer.start()

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def _handle(self, path: str):
        p = Path(path)
        if p.suffix.lower() == ".md" and "01-Import" in str(p):
            self._pending.add(path)
            self._log(f"[WATCH] 文件变化: {p.name}")
            self._schedule_sync()


class KBSyncDaemon:
    """同步守护进程管理"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()
        self.pid_file = self.vault_path / ".sync.pid"
        self._log_dir = self.vault_path.parent / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _log(self, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        log_file = self._log_dir / "sync.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)

    def start(self):
        if not WATCHDOG_AVAILABLE:
            print("[ERR] watchdog 未安装，请运行: pip install watchdog")
            return

        if self.pid_file.exists():
            pid = self._read_pid()
            if pid and self._is_alive(pid):
                print(f"[WARN]  守护进程已在运行 (PID: {pid})")
                return

        pid = os.getpid()
        self.pid_file.write_text(str(pid), encoding="utf-8")

        self._log(f"[START] KB同步守护进程启动 (PID: {pid})")
        self._log(f"[WATCH] 监听目录: {self.vault_path / '01-Import'}")

        handler = KBFileHandler(self.vault_path)
        observer = Observer()
        watch_dir = self.vault_path / "01-Import"
        watch_dir.mkdir(parents=True, exist_ok=True)
        observer.schedule(handler, str(watch_dir), recursive=False)
        observer.start()

        def _shutdown(sig, frame):
            self._log("[STOP] 收到停止信号，正在退出...")
            observer.stop()
            observer.join()
            self.pid_file.unlink(missing_ok=True)
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            observer.join()
            self.pid_file.unlink(missing_ok=True)
            self._log("[STOP] 守护进程已停止")

    def stop(self):
        if not self.pid_file.exists():
            print("[INFO]  守护进程未运行")
            return

        pid = self._read_pid()
        if pid and self._is_alive(pid):
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True)
                else:
                    os.kill(pid, signal.SIGTERM)
                self._log(f"[STOP] 已停止守护进程 (PID: {pid})")
            except OSError as e:
                print(f"[ERR] 停止失败: {e}")
        else:
            print("[INFO]  进程已不存在")

        self.pid_file.unlink(missing_ok=True)

    def status(self):
        if not self.pid_file.exists():
            print("[STATUS] 守护进程: 未运行")
            return

        pid = self._read_pid()
        if pid and self._is_alive(pid):
            print(f"[STATUS] 守护进程: 运行中 (PID: {pid})")
        else:
            print("[STATUS] 守护进程: 已停止 (残留PID文件)")
            self.pid_file.unlink(missing_ok=True)

        log_file = self._log_dir / "sync.log"
        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            print(f"\n最近日志 (最后5条):")
            for line in lines[-5:]:
                print(f"  {line}")

    def _read_pid(self):
        try:
            return int(self.pid_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            return None

    def _is_alive(self, pid: int) -> bool:
        try:
            if sys.platform == "win32":
                result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                       capture_output=True, text=True, encoding="utf-8", errors="replace")
                return str(pid) in result.stdout
            else:
                os.kill(pid, 0)
                return True
        except (OSError, subprocess.SubprocessError):
            return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="KB Sync Daemon")
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--vault", default="./AI知识库")
    args = parser.parse_args()

    daemon = KBSyncDaemon(args.vault)
    if args.action == "start":
        daemon.start()
    elif args.action == "stop":
        daemon.stop()
    elif args.action == "status":
        daemon.status()


if __name__ == "__main__":
    main()
