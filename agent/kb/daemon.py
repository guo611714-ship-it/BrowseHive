"""daemon.py - Unified daemon manager for AI Knowledge Base

Combines: daemon_core + daemon_logging + daemon_startup + kb_daemon.

CLI:
    python daemon.py start [sync|backup|cache|all]
    python daemon.py stop [sync|backup|cache|all]
    python daemon.py restart [sync|backup|cache|all]
    python daemon.py status
    python daemon.py health
    python daemon.py monitor
    python daemon.py install-startup
    python daemon.py uninstall-startup
"""

import logging
import argparse
import json
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .utils import is_alive, kill_pid

logger = logging.getLogger(__name__)

SERVICES = ("sync", "backup", "cache")
HEARTBEAT_INTERVAL_SEC = 60
HEARTBEAT_TIMEOUT_SEC = 300
HEALTH_CHECK_INTERVAL_SEC = 30
SCRIPT_DIR = Path(__file__).resolve().parent  # agent/kb/


# ---------------------------------------------------------------------------
#  Logging helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_info(msg: str):
    print(f"[{_ts()}] [INFO]  {msg}")


def log_ok(msg: str):
    print(f"[{_ts()}] [OK]    {msg}")


def log_warn(msg: str):
    print(f"[{_ts()}] [WARN]  {msg}")


def log_err(msg: str):
    print(f"[{_ts()}] [ERR]   {msg}")


def log_start(msg: str):
    print(f"[{_ts()}] [START] {msg}")


def log_stop(msg: str):
    print(f"[{_ts()}] [STOP]  {msg}")


# ---------------------------------------------------------------------------
#  Daemon core - PID/heartbeat/health check/service management
# ---------------------------------------------------------------------------

class KBDaemonCore:
    """Unified daemon process manager for sync / backup / cache services."""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).resolve()
        self.daemon_dir = self.vault_path / ".daemon"
        self.daemon_dir.mkdir(parents=True, exist_ok=True)
        self.pid_file = self.daemon_dir / "pids.json"
        self.health_file = self.daemon_dir / "health.json"
        self.heartbeat_file = self.daemon_dir / "heartbeat.json"
        self.log_dir = self.vault_path.parent / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    # -- Internal helpers --

    def _read_pids(self) -> dict:
        if self.pid_file.exists():
            try:
                with open(self.pid_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write_pids(self, pids: dict):
        with open(self.pid_file, "w", encoding="utf-8") as f:
            json.dump(pids, f, indent=2, ensure_ascii=False)

    def _read_heartbeat(self) -> dict:
        if self.heartbeat_file.exists():
            try:
                with open(self.heartbeat_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write_heartbeat(self, data: dict):
        with open(self.heartbeat_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _read_health(self) -> dict:
        if self.health_file.exists():
            try:
                with open(self.health_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write_health(self, data: dict):
        with open(self.health_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _get_service_script(self, service: str) -> Optional[Path]:
        mapping = {
            "sync": SCRIPT_DIR / "kb_sync.py",
            "backup": SCRIPT_DIR / "kb_backup.py",
            "cache": SCRIPT_DIR / "kb_cache.py",
        }
        script = mapping.get(service)
        if script and script.exists():
            return script
        return None

    def _normalize_services(self, services: Optional[list]) -> list:
        if services is None or services == ["all"]:
            return list(SERVICES)
        result = []
        for s in services:
            s = s.strip().lower()
            if s in SERVICES:
                result.append(s)
            else:
                log_warn(f"Unknown service: {s}, skipped")
        return result

    # -- Commands --

    def start(self, services: Optional[list] = None):
        targets = self._normalize_services(services)
        pids = self._read_pids()

        for svc in targets:
            old_pid = pids.get(svc)
            if old_pid and is_alive(old_pid):
                log_warn(f"{svc} already running (PID: {old_pid})")
                continue

            script = self._get_service_script(svc)
            if script is None:
                log_err(f"{svc}: script not found, skipped")
                continue

            cmd = [sys.executable, str(script), "start", "--vault", str(self.vault_path)]
            if svc == "backup":
                cmd.extend(["--interval", "3600"])

            log_start(f"Starting {svc}: {' '.join(cmd)}")
            try:
                log_file = self.log_dir / f"{svc}_daemon.log"
                with open(log_file, "a", encoding="utf-8") as lf:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=lf,
                        stderr=subprocess.STDOUT,
                        encoding="utf-8",
                        errors="replace",
                        cwd=str(SCRIPT_DIR),
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                        if sys.platform == "win32" else 0,
                    )
                pids[svc] = proc.pid
                log_ok(f"{svc} started (PID: {proc.pid})")
            except Exception as e:
                log_err(f"{svc} start failed: {e}")

        self._write_pids(pids)

    def stop(self, services: Optional[list] = None):
        targets = self._normalize_services(services)
        pids = self._read_pids()

        for svc in targets:
            pid = pids.get(svc)
            if pid is None:
                log_info(f"{svc} not tracked (no PID)")
                continue

            if is_alive(pid):
                log_stop(f"Stopping {svc} (PID: {pid})")
                kill_pid(pid)
                log_ok(f"{svc} stopped")
            else:
                log_info(f"{svc} process {pid} already dead")

            pids.pop(svc, None)

        self._write_pids(pids)

        # Clean up legacy PID files
        for name, legacy_file in [
            ("sync", self.vault_path / ".sync.pid"),
            ("backup", self.vault_path / ".backup.pid"),
        ]:
            if name in targets and legacy_file.exists():
                try:
                    legacy_file.unlink()
                except OSError:
                    pass

    def restart(self, services: Optional[list] = None):
        self.stop(services)
        time.sleep(1)
        self.start(services)

    def status(self):
        pids = self._read_pids()
        heartbeats = self._read_heartbeat()
        now = datetime.now()

        print()
        print(f"  Service   | PID     | Status   | Uptime       | Last Heartbeat")
        print(f"  -----------+---------+----------+--------------+----------------")

        for svc in SERVICES:
            pid = pids.get(svc)
            hb_str = heartbeats.get(svc, "never")

            if pid and is_alive(pid):
                status = "running"
                hb_time = heartbeats.get(svc)
                if hb_time:
                    try:
                        hb_dt = datetime.fromisoformat(hb_time)
                        uptime = now - hb_dt
                        uptime_str = str(uptime).split(".")[0]
                    except (ValueError, TypeError):
                        uptime_str = "unknown"
                else:
                    uptime_str = "unknown"
            else:
                status = "stopped"
                uptime_str = "-"
                hb_str = "-"

            print(f"  {svc:9s} | {str(pid or '-'):7s} | {status:8s} | {uptime_str:12s} | {hb_str}")

        print()
        return pids

    def health_check(self):
        pids = self._read_pids()
        heartbeats = self._read_heartbeat()
        now = datetime.now()
        health_report = {}
        restarted = []

        for svc in SERVICES:
            pid = pids.get(svc)
            entry = {"status": "stopped", "pid": None, "last_heartbeat": None, "action": "none"}

            if pid:
                alive = is_alive(pid)
                entry["pid"] = pid

                if alive:
                    hb_time = heartbeats.get(svc)
                    entry["last_heartbeat"] = hb_time

                    if hb_time:
                        try:
                            hb_dt = datetime.fromisoformat(hb_time)
                            age = (now - hb_dt).total_seconds()
                        except (ValueError, TypeError):
                            age = 0

                        if age > HEARTBEAT_TIMEOUT_SEC:
                            entry["status"] = "stale"
                            entry["action"] = "restarting"
                            log_warn(
                                f"{svc}: heartbeat stale ({int(age)}s > {HEARTBEAT_TIMEOUT_SEC}s), "
                                f"auto-restarting"
                            )
                            self.stop([svc])
                            restarted.append(svc)
                        else:
                            entry["status"] = "healthy"
                    else:
                        entry["status"] = "starting"
                else:
                    entry["status"] = "dead"
                    entry["action"] = "restarting"
                    log_warn(f"{svc}: process dead, auto-restarting")
                    pids.pop(svc, None)
                    self._write_pids(pids)
                    restarted.append(svc)
            else:
                entry["status"] = "not_tracked"

            health_report[svc] = entry

        if restarted:
            time.sleep(1)
            self.start(restarted)

        health_report["_timestamp"] = now.isoformat()
        health_report["_checked_services"] = SERVICES
        self._write_health(health_report)
        return health_report

    def write_daemon_heartbeat(self, service: str):
        heartbeats = self._read_heartbeat()
        heartbeats[service] = datetime.now().isoformat()
        self._write_heartbeat(heartbeats)

    def monitor_loop(self):
        log_info(f"Health monitor started (interval: {HEALTH_CHECK_INTERVAL_SEC}s)")
        try:
            while True:
                self.health_check()
                time.sleep(HEALTH_CHECK_INTERVAL_SEC)
        except KeyboardInterrupt:
            log_info("Health monitor stopped")


# ---------------------------------------------------------------------------
#  Startup installation - Windows/Linux/macOS auto-start
# ---------------------------------------------------------------------------

class StartupMixin:
    """Mixin: install/uninstall OS-level auto-start for KBDaemonCore."""

    def install_startup(self):
        system = platform.system()
        if system == "Windows":
            self._install_startup_windows()
        elif system == "Linux":
            self._install_startup_linux()
        elif system == "Darwin":
            self._install_startup_macos()
        else:
            log_err(f"Unsupported platform: {system}")

    def uninstall_startup(self):
        system = platform.system()
        if system == "Windows":
            self._uninstall_startup_windows()
        elif system == "Linux":
            self._uninstall_startup_linux()
        elif system == "Darwin":
            self._uninstall_startup_macos()
        else:
            log_err(f"Unsupported platform: {system}")

    # -- Windows: schtasks --

    def _install_startup_windows(self):
        task_name = "AIKB_DaemonManager"
        cmd = (
            f'schtasks /Create /TN "{task_name}" /TR '
            f'"{sys.executable} {Path(__file__).resolve()} health" '
            f'/SC MINUTE /MO 5 /F'
        )
        try:
            result = subprocess.run(
                cmd, shell=True,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=15,
            )
            if result.returncode == 0:
                log_ok(f"Windows startup task created: {task_name}")
            else:
                log_err(f"Failed: {result.stderr.strip()}")
        except Exception as e:
            log_err(f"Failed to create startup task: {e}")

        start_task = "AIKB_StartAll"
        start_cmd = (
            f'schtasks /Create /TN "{start_task}" /TR '
            f'"{sys.executable} {Path(__file__).resolve()} start all" '
            f'/SC ONLOGON /F'
        )
        try:
            result = subprocess.run(
                start_cmd, shell=True,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=15,
            )
            if result.returncode == 0:
                log_ok(f"Windows logon task created: {start_task}")
            else:
                log_err(f"Failed: {result.stderr.strip()}")
        except Exception as e:
            log_err(f"Failed to create logon task: {e}")

    def _uninstall_startup_windows(self):
        for task_name in ["AIKB_DaemonManager", "AIKB_StartAll"]:
            try:
                result = subprocess.run(
                    f'schtasks /Delete /TN "{task_name}" /F',
                    shell=True,
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=15,
                )
                if result.returncode == 0:
                    log_ok(f"Windows task removed: {task_name}")
                else:
                    log_warn(f"Task {task_name} not found or already removed")
            except Exception as e:
                log_warn(f"Failed to remove {task_name}: {e}")

    # -- Linux: systemd --

    def _install_startup_linux(self):
        service_name = "ai-kb-daemon"
        daemon_dir = Path.home() / ".config" / "systemd" / "user"
        daemon_dir.mkdir(parents=True, exist_ok=True)
        service_file = daemon_dir / f"{service_name}.service"

        content = f"""\
[Unit]
Description=AI Knowledge Base Daemon Manager
After=network.target

[Service]
Type=simple
ExecStart={sys.executable} {Path(__file__).resolve()} monitor
Restart=on-failure
RestartSec=30
WorkingDirectory={SCRIPT_DIR}

[Install]
WantedBy=default.target
"""
        try:
            service_file.write_text(content, encoding="utf-8")
            log_ok(f"Systemd service written: {service_file}")

            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["systemctl", "--user", "enable", service_name],
                capture_output=True, timeout=10,
            )
            log_ok(f"Systemd service enabled: {service_name}")
        except Exception as e:
            log_err(f"Failed to install systemd service: {e}")

    def _uninstall_startup_linux(self):
        service_name = "ai-kb-daemon"
        try:
            subprocess.run(
                ["systemctl", "--user", "disable", service_name],
                capture_output=True, timeout=10,
            )
            service_file = (
                Path.home() / ".config" / "systemd" / "user"
                / f"{service_name}.service"
            )
            if service_file.exists():
                service_file.unlink()
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True, timeout=10,
            )
            log_ok(f"Systemd service removed: {service_name}")
        except Exception as e:
            log_warn(f"Failed to remove systemd service: {e}")

    # -- macOS: launchd --

    def _install_startup_macos(self):
        plist_name = "com.ai.kb-daemon"
        plist_dir = Path.home() / "Library" / "LaunchAgents"
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_file = plist_dir / f"{plist_name}.plist"

        content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{plist_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{Path(__file__).resolve()}</string>
        <string>monitor</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{SCRIPT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{self.log_dir / "daemon_launchd.log"}</string>
    <key>StandardErrorPath</key>
    <string>{self.log_dir / "daemon_launchd_err.log"}</string>
</dict>
</plist>
"""
        try:
            plist_file.write_text(content, encoding="utf-8")
            subprocess.run(
                ["launchctl", "unload", str(plist_file)],
                capture_output=True, timeout=10,
            )
            result = subprocess.run(
                ["launchctl", "load", str(plist_file)],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=10,
            )
            if result.returncode == 0:
                log_ok(f"Launchd plist loaded: {plist_name}")
            else:
                log_err(f"Failed to load: {result.stderr.strip()}")
        except Exception as e:
            log_err(f"Failed to install launchd service: {e}")

    def _uninstall_startup_macos(self):
        plist_name = "com.ai.kb-daemon"
        plist_file = (
            Path.home() / "Library" / "LaunchAgents" / f"{plist_name}.plist"
        )
        try:
            subprocess.run(
                ["launchctl", "unload", str(plist_file)],
                capture_output=True, timeout=10,
            )
            if plist_file.exists():
                plist_file.unlink()
            log_ok(f"Launchd service removed: {plist_name}")
        except Exception as e:
            log_warn(f"Failed to remove launchd service: {e}")


# ---------------------------------------------------------------------------
#  Combined daemon manager
# ---------------------------------------------------------------------------

class KBDaemonManager(StartupMixin, KBDaemonCore):
    """Combined daemon manager: core + startup installation."""
    pass


def heartbeat_writer(daemon_manager: KBDaemonManager, service: str):
    """Run in a background thread to update heartbeat every HEARTBEAT_INTERVAL_SEC."""

    def _loop():
        while True:
            try:
                daemon_manager.write_daemon_heartbeat(service)
            except Exception as e:
                logger.debug("心跳写入失败: %s", e)
            time.sleep(HEARTBEAT_INTERVAL_SEC)

    t = threading.Thread(target=_loop, daemon=True, name=f"heartbeat-{service}")
    t.start()
    return t


def main():
    parser = argparse.ArgumentParser(
        description="AI Knowledge Base - Unified Daemon Manager"
    )
    parser.add_argument(
        "action",
        choices=[
            "start", "stop", "restart", "status",
            "health", "monitor",
            "install-startup", "uninstall-startup",
        ],
        help="Action to perform",
    )
    parser.add_argument(
        "service",
        nargs="?",
        default="all",
        help="Service name: sync, backup, cache, or all (default: all)",
    )
    parser.add_argument(
        "--vault",
        default=str(SCRIPT_DIR / "AI知识库"),
        help="Path to the knowledge base vault (default: ./AI知识库)",
    )
    args = parser.parse_args()

    manager = KBDaemonManager(args.vault)
    services = None if args.service == "all" else [args.service]

    if args.action == "start":
        manager.start(services)
    elif args.action == "stop":
        manager.stop(services)
    elif args.action == "restart":
        manager.restart(services)
    elif args.action == "status":
        manager.status()
    elif args.action == "health":
        report = manager.health_check()
        print()
        for svc, info in report.items():
            if svc.startswith("_"):
                continue
            print(f"  {svc}: {info.get('status', 'unknown')}")
        print()
    elif args.action == "monitor":
        manager.monitor_loop()
    elif args.action == "install-startup":
        manager.install_startup()
    elif args.action == "uninstall-startup":
        manager.uninstall_startup()


if __name__ == "__main__":
    main()
