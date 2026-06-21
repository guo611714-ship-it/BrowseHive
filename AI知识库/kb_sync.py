#!/usr/bin/env python3
"""
KB File Sync Daemon
自动监听 Obsidian vault 文件变化并增量同步索引。

依赖: pip install watchdog
用法:
    python kb_sync.py start    启动守护进程
    python kb_sync.py stop     停止守护进程
    python kb_sync.py status   查看运行状态
"""

import json
import sys
import time
import signal
import logging
import threading
import subprocess
from pathlib import Path
from datetime import datetime

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("[ERR] watchdog not installed. Run: pip install watchdog")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
VAULT_PATH = SCRIPT_DIR
IMPORT_DIR = VAULT_PATH / "01-Import"
INDEX_FILE = VAULT_PATH / "03-Index" / "documents.json"
PID_FILE = VAULT_PATH / ".sync.pid"
LOG_DIR = VAULT_PATH.parent / "logs"
LOG_FILE = LOG_DIR / "sync.log"
DEBOUNCE_SEC = 5

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("kb_sync")
logger.setLevel(logging.INFO)
_fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setFormatter(_fmt)
logger.addHandler(_fh)
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
logger.addHandler(_sh)


# ---------------------------------------------------------------------------
# Index helper
# ---------------------------------------------------------------------------
def _load_index() -> dict:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return {"documents": []}


def _save_index(data: dict):
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_title(filepath: Path) -> str:
    """从文件名提取标题 -- 去掉 hash 前缀和扩展名"""
    stem = filepath.stem
    parts = stem.split("-", 1)
    if len(parts) == 2 and len(parts[0]) == 8:
        return parts[1]
    return stem


def _sync_single_file(filepath: Path, index: dict) -> str:
    """同步单个文件到索引，返回 'added' / 'updated' / 'skipped'"""
    rel = filepath.relative_to(VAULT_PATH)
    rel_str = str(rel).replace("\\", "/")

    # 检查是否已存在
    for i, doc in enumerate(index["documents"]):
        doc_path = doc.get("path", "").replace("\\", "/")
        if doc_path == rel_str:
            # 更新
            index["documents"][i]["title"] = _extract_title(filepath)
            index["documents"][i]["updated"] = datetime.now().isoformat()
            return "updated"

    # 新增
    index["documents"].append({
        "path": rel_str,
        "title": _extract_title(filepath),
        "entities": [],
        "concepts": [],
        "tags": [],
        "created": datetime.now().isoformat(),
    })
    return "added"


def _remove_from_index(filepath: Path, index: dict) -> bool:
    rel = filepath.relative_to(VAULT_PATH)
    rel_str = str(rel).replace("\\", "/")
    before = len(index["documents"])
    index["documents"] = [
        d for d in index["documents"]
        if d.get("path", "").replace("\\", "/") != rel_str
    ]
    return len(index["documents"]) < before


# ---------------------------------------------------------------------------
# Watchdog handler with debounce
# ---------------------------------------------------------------------------
class KBFileHandler(FileSystemEventHandler):
    def __init__(self, kb_manager: "KBSyncDaemon"):
        self.kb = kb_manager
        self._pending: set = set()
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def _schedule_flush(self):
        """重置 debounce timer"""
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(DEBOUNCE_SEC, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _flush(self):
        """debounce 到期后执行同步"""
        with self._lock:
            pending = list(self._pending)
            self._pending.clear()
            self._timer = None

        if not pending:
            return

        logger.info("Debounce fired -- syncing %d file(s)", len(pending))
        self.kb.do_sync(pending)

    def _queue(self, event):
        if event.is_directory:
            return
        src = Path(event.src_path)
        if not IMPORT_DIR in src.parents and src != IMPORT_DIR:
            return
        if not src.suffix.lower() in (".md", ".txt", ".json"):
            return
        with self._lock:
            self._pending.add(str(src))
        self._schedule_flush()

    def on_modified(self, event):
        self._queue(event)

    def on_created(self, event):
        self._queue(event)

    def on_deleted(self, event):
        self._queue(event)

    def on_moved(self, event):
        # move = delete old + create new
        self._queue(event)
        if hasattr(event, "dest_path"):
            self._queue(event)


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------
class KBSyncDaemon:
    def __init__(self, vault_path: Path | str = VAULT_PATH):
        self.vault_path = Path(vault_path).resolve()
        self.pid_file = self.vault_path / ".sync.pid"
        self._observer: Observer | None = None

    # -- sync logic --------------------------------------------------------
    def do_sync(self, file_paths: list[str] | None = None):
        """执行增量同步"""
        index = _load_index()
        added, updated, removed = 0, 0, 0

        if file_paths is not None:
            # 增量: 只处理传入的文件
            for fp_str in file_paths:
                fp = Path(fp_str)
                if not fp.exists():
                    # 文件被删除
                    if _remove_from_index(fp, index):
                        removed += 1
                        logger.info("  [DEL] %s", fp.name)
                    continue
                result = _sync_single_file(fp, index)
                if result == "added":
                    added += 1
                    logger.info("  [ADD] %s", fp.name)
                elif result == "updated":
                    updated += 1
                    logger.info("  [UPD] %s", fp.name)
        else:
            # 全量: 扫描整个目录
            existing = {
                d.get("path", "").replace("\\", "/")
                for d in index["documents"]
            }
            found = set()

            for f in sorted(IMPORT_DIR.rglob("*")):
                if f.is_file() and f.suffix.lower() in (".md", ".txt", ".json"):
                    rel = f.relative_to(self.vault_path)
                    rel_str = str(rel).replace("\\", "/")
                    found.add(rel_str)
                    result = _sync_single_file(f, index)
                    if result == "added":
                        added += 1
                    elif result == "updated":
                        updated += 1

            # 删除不存在的
            gone = existing - found
            for g in gone:
                for doc in index["documents"][:]:
                    if doc.get("path", "").replace("\\", "/") == g:
                        index["documents"].remove(doc)
                        removed += 1
                        break

        _save_index(index)
        total = len(index["documents"])
        logger.info(
            "Sync done: +%d added, ~%d updated, -%d removed (total %d)",
            added, updated, removed, total,
        )

    # -- start -------------------------------------------------------------
    def start(self):
        if self._is_running():
            pid = self.pid_file.read_text().strip()
            print(f"[WARN] Daemon already running (PID {pid})")
            return

        # 确保 import 目录存在
        IMPORT_DIR.mkdir(parents=True, exist_ok=True)

        # 首次全量同步
        logger.info("Running initial full sync ...")
        self.do_sync()

        # 启动 watchdog
        handler = KBFileHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(IMPORT_DIR), recursive=True)
        self._observer.start()

        # 写 PID (守护进程运行在当前进程)
        import os
        pid = os.getpid()
        self.pid_file.write_text(str(pid))
        logger.info("Daemon started (PID %d), watching %s", pid, IMPORT_DIR)
        print(f"[OK] Daemon started (PID {pid})")

        try:
            signal.signal(signal.SIGINT, lambda *_: self.stop())
            signal.signal(signal.SIGTERM, lambda *_: self.stop())
        except (OSError, ValueError):
            pass  # Windows 不支持某些信号

        try:
            while self._observer.is_alive():
                self._observer.join(timeout=1)
        except KeyboardInterrupt:
            self.stop()

    # -- stop --------------------------------------------------------------
    def stop(self):
        if not self.pid_file.exists():
            print("[WARN] No PID file found -- daemon may not be running")
            return

        pid = int(self.pid_file.read_text().strip())
        logger.info("Stopping daemon (PID %d) ...", pid)

        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5)

        # 尝试 kill 残留进程
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                )
            else:
                import os
                os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass

        self.pid_file.unlink(missing_ok=True)
        logger.info("Daemon stopped")
        print("[OK] Daemon stopped")

    # -- status ------------------------------------------------------------
    def status(self) -> bool:
        if not self.pid_file.exists():
            print("[INFO] Daemon is not running (no PID file)")
            return False

        pid = int(self.pid_file.read_text().strip())
        alive = self._check_pid(pid)
        if alive:
            print(f"[OK] Daemon running (PID {pid})")
        else:
            print(f"[WARN] PID {pid} not alive -- cleaning up stale PID file")
            self.pid_file.unlink(missing_ok=True)
        return alive

    def _is_running(self) -> bool:
        if not self.pid_file.exists():
            return False
        pid = int(self.pid_file.read_text().strip())
        return self._check_pid(pid)

    @staticmethod
    def _check_pid(pid: int) -> bool:
        """检查进程是否存活"""
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True, text=True,
                )
                return str(pid) in result.stdout
            else:
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, OSError):
            return False


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python kb_sync.py [start|stop|status]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    daemon = KBSyncDaemon()

    if cmd == "start":
        daemon.start()
    elif cmd == "stop":
        daemon.stop()
    elif cmd == "status":
        daemon.status()
    elif cmd == "sync":
        # 手动触发一次全量同步
        logger.info("Manual full sync triggered")
        daemon.do_sync()
        print("[OK] Full sync completed")
    else:
        print(f"[ERR] Unknown command: {cmd}")
        print("Usage: python kb_sync.py [start|stop|status|sync]")
        sys.exit(1)


if __name__ == "__main__":
    main()
