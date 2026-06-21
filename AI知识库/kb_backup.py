#!/usr/bin/env python3
"""
KB Auto Git Backup
定时自动备份知识库到 git。

用法:
    python kb_backup.py run      执行一次备份
    python kb_backup.py start    启动定时备份（每小时）
    python kb_backup.py status   查看上次备份状态
    python kb_backup.py init     初始化 git 仓库（如果不存在）
"""

import json
import sys
import time
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
VAULT_PATH = SCRIPT_DIR
STATE_FILE = VAULT_PATH / ".backup_state.json"
PID_FILE = VAULT_PATH / ".backup.pid"
LOG_DIR = VAULT_PATH.parent / "logs"
LOG_FILE = LOG_DIR / "backup.log"
BACKUP_INTERVAL_SEC = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("kb_backup")
logger.setLevel(logging.INFO)
_fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setFormatter(_fmt)
logger.addHandler(_fh)
_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
logger.addHandler(_sh)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------
def _load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------
def _run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """在 vault 目录下执行 git 命令"""
    result = subprocess.run(
        ["git"] + args,
        cwd=str(VAULT_PATH),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result


def _is_git_repo() -> bool:
    result = _run_git(["rev-parse", "--is-inside-work-tree"], check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def _init_git():
    """初始化 git 仓库"""
    if _is_git_repo():
        logger.info("Git repo already initialized")
        return

    _run_git(["init"])
    # 创建 .gitignore
    gitignore = VAULT_PATH / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
        ".sync.pid\n"
        ".backup.pid\n"
        ".backup_state.json\n"
        ".obsidian/\n"
        "__pycache__/\n"
        "*.pyc\n"
        ".env\n"
        "*.env\n",
        encoding="utf-8",
    )
    _run_git(["add", ".gitignore"])
    _run_git(["commit", "-m", "init: knowledge base repository"])
    logger.info("Git repo initialized")


def _has_changes() -> bool:
    """检查是否有未提交的变更"""
    _run_git(["add", "-A", "--", ":!.env", ":!*.env"])
    result = _run_git(["diff", "--cached", "--stat"], check=False)
    return bool(result.stdout.strip())


def _count_changed_files() -> int:
    result = _run_git(["diff", "--cached", "--numstat"], check=False)
    if not result.stdout.strip():
        return 0
    return len(result.stdout.strip().split("\n"))


def _commit(message: str):
    _run_git(["commit", "-m", message])
    logger.info("Committed: %s", message)


def _get_last_commit_time() -> str | None:
    result = _run_git(
        ["log", "-1", "--format=%ci"],
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


# ---------------------------------------------------------------------------
# Backup logic
# ---------------------------------------------------------------------------
def do_backup() -> bool:
    """执行一次备份。返回是否有变更被提交"""
    if not _is_git_repo():
        logger.warning("Not a git repo -- run 'python kb_backup.py init' first")
        print("[WARN] Not a git repo. Run: python kb_backup.py init")
        return False

    if not _has_changes():
        logger.info("No changes to backup")
        print("[OK] No changes")
        return False

    n_files = _count_changed_files()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_msg = f"auto-backup: {now} ({n_files} files changed)"
    _commit(commit_msg)

    state = _load_state()
    state["last_backup"] = datetime.now().isoformat()
    state["last_commit_msg"] = commit_msg
    state["files_changed"] = n_files
    _save_state(state)

    print(f"[OK] Backed up: {n_files} files")
    return True


# ---------------------------------------------------------------------------
# Daemon (timer-based loop, Windows-compatible)
# ---------------------------------------------------------------------------
class BackupDaemon:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self):
        logger.info("Backup daemon started, interval %d sec", BACKUP_INTERVAL_SEC)
        while not self._stop_event.is_set():
            try:
                do_backup()
            except Exception as exc:
                logger.error("Backup failed: %s", exc, exc_info=True)
            self._stop_event.wait(BACKUP_INTERVAL_SEC)

    def start(self):
        if self._is_running():
            pid = PID_FILE.read_text().strip()
            print(f"[WARN] Daemon already running (PID {pid})")
            return

        pid = __import__("os").getpid()
        PID_FILE.write_text(str(pid))
        logger.info("Starting backup daemon (PID %d)", pid)
        print(f"[OK] Backup daemon started (PID {pid})")

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        try:
            self._thread.join()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if not PID_FILE.exists():
            print("[WARN] No PID file -- daemon may not be running")
            return

        pid = int(PID_FILE.read_text().strip())
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        PID_FILE.unlink(missing_ok=True)
        logger.info("Backup daemon stopped (PID %d)", pid)
        print("[OK] Backup daemon stopped")

    def status(self) -> dict:
        state = _load_state()
        running = self._is_running()

        info = {
            "running": running,
            "pid": None,
            "last_backup": state.get("last_backup"),
            "last_commit_msg": state.get("last_commit_msg"),
            "files_changed": state.get("files_changed"),
            "last_commit_time": _get_last_commit_time() if _is_git_repo() else None,
        }

        if PID_FILE.exists():
            info["pid"] = PID_FILE.read_text().strip()

        # 打印
        if running:
            print(f"[OK] Daemon running (PID {info['pid']})")
        else:
            print("[INFO] Daemon not running")

        if info["last_backup"]:
            print(f"    Last backup: {info['last_backup']}")
        if info["last_commit_msg"]:
            print(f"    Last commit: {info['last_commit_msg']}")
        if info["last_commit_time"]:
            print(f"    Git last commit: {info['last_commit_time']}")

        return info

    def _is_running(self) -> bool:
        if not PID_FILE.exists():
            return False
        pid = int(PID_FILE.read_text().strip())
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True, text=True,
                )
                return str(pid) in result.stdout
            else:
                import os
                os.kill(pid, 0)
                return True
        except (ProcessLookupError, OSError, ValueError):
            return False


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python kb_backup.py [init|run|start|stop|status]")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    daemon = BackupDaemon()

    if cmd == "init":
        _init_git()
        print("[OK] Git repository initialized")

    elif cmd == "run":
        do_backup()

    elif cmd == "start":
        daemon.start()

    elif cmd == "stop":
        daemon.stop()

    elif cmd == "status":
        daemon.status()

    else:
        print(f"[ERR] Unknown command: {cmd}")
        print("Usage: python kb_backup.py [init|run|start|stop|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()
