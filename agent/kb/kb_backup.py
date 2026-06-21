#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KB Backup Daemon - 自动 git 备份知识库

定期检查知识库变更，自动 commit。
支持 run / start / stop / status 命令。
"""

import os
import sys
import json
import time
import signal
import subprocess
from pathlib import Path
from datetime import datetime


class KBBackupDaemon:
    """Git 自动备份"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()
        self.state_file = self.vault_path / ".backup_state.json"
        self.pid_file = self.vault_path / ".backup.pid"
        self._log_dir = self.vault_path.parent / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _log(self, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        log_file = self._log_dir / "backup.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)

    def _load_state(self) -> dict:
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"last_backup": None, "total_backups": 0}

    def _save_state(self, state: dict):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def run(self) -> bool:
        """执行一次备份，返回是否有变更"""
        try:
            subprocess.run(
                ["git", "add", "."],
                cwd=str(self.vault_path),
                capture_output=True,
                timeout=30,
            )

            result = subprocess.run(
                ["git", "diff", "--cached", "--stat"],
                cwd=str(self.vault_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )

            if not result.stdout.strip():
                self._log("[BACKUP] 知识库无变更")
                return False

            file_count = result.stdout.count("\n")

            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            message = f"auto-backup: {ts} ({file_count} files changed)"
            commit_result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.vault_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )

            if commit_result.returncode == 0:
                self._log(f"[BACKUP] 已备份: {message}")
                state = self._load_state()
                state["last_backup"] = datetime.now().isoformat()
                state["total_backups"] = state.get("total_backups", 0) + 1
                self._save_state(state)
                return True
            else:
                self._log(f"[WARN]  提交失败: {commit_result.stderr.strip()}")
                return False

        except subprocess.TimeoutExpired:
            self._log("[ERR] git 操作超时")
            return False
        except Exception as e:
            self._log(f"[ERR] 备份失败: {e}")
            return False

    def start(self, interval_sec: int = 3600):
        if self.pid_file.exists():
            pid = self._read_pid()
            if pid and self._is_alive(pid):
                print(f"[WARN]  备份任务已在运行 (PID: {pid})")
                return

        pid = os.getpid()
        self.pid_file.write_text(str(pid), encoding="utf-8")
        self._log(f"[START] 定时备份启动 (PID: {pid}), 间隔 {interval_sec}s")

        def _shutdown(sig, frame):
            self._log("[STOP] 备份任务停止")
            self.pid_file.unlink(missing_ok=True)
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        while True:
            self.run()
            time.sleep(interval_sec)

    def stop(self):
        if not self.pid_file.exists():
            print("[INFO]  备份任务未运行")
            return

        pid = self._read_pid()
        if pid and self._is_alive(pid):
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                   capture_output=True)
                else:
                    os.kill(pid, signal.SIGTERM)
                self._log(f"[STOP] 已停止备份任务 (PID: {pid})")
            except OSError as e:
                print(f"[ERR] 停止失败: {e}")
        else:
            print("[INFO]  进程已不存在")

        self.pid_file.unlink(missing_ok=True)

    def status(self):
        state = self._load_state()
        print("[STATUS] 知识库备份状态:")
        print(f"  上次备份: {state.get('last_backup', '从未')}")
        print(f"  累计备份: {state.get('total_backups', 0)} 次")

        if self.pid_file.exists():
            pid = self._read_pid()
            if pid and self._is_alive(pid):
                print(f"  定时任务: 运行中 (PID: {pid})")
            else:
                print("  定时任务: 已停止")
        else:
            print("  定时任务: 未启动")

        log_file = self._log_dir / "backup.log"
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
    parser = argparse.ArgumentParser(description="KB Backup Daemon")
    parser.add_argument("action", choices=["run", "start", "stop", "status"])
    parser.add_argument("--vault", default="./AI知识库")
    parser.add_argument("--interval", type=int, default=3600)
    args = parser.parse_args()

    daemon = KBBackupDaemon(args.vault)
    if args.action == "run":
        daemon.run()
    elif args.action == "start":
        daemon.start(args.interval)
    elif args.action == "stop":
        daemon.stop()
    elif args.action == "status":
        daemon.status()


if __name__ == "__main__":
    main()
