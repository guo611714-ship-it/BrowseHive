"""监控和会话管理."""

import os
import time
import json
import asyncio
import shutil
from typing import Optional, Dict, Any
from pathlib import Path

from .config import config
from .platforms import PLATFORMS
try:
    from browser_agent import get_browser_agent
    BROWSER_AGENT_AVAILABLE = True
except ImportError:
    BROWSER_AGENT_AVAILABLE = False
    def get_browser_agent():
        return None
from .chat_engine import chat_engine
from .cache_manager import cache_manager


def _check_disk_space(path: str = "/") -> Dict[str, Any]:
    """检查磁盘空间."""
    try:
        usage = shutil.disk_usage(path)
        return {
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
            "percent_used": round(usage.used / usage.total * 100, 1),
        }
    except Exception:
        return {"error": "无法获取磁盘信息"}


def _check_network_latency(host: str = "cloudflare.com", timeout: int = 2) -> Optional[float]:
    """检查网络延迟（ICMP ping 近似，返回毫秒）."""
    import socket
    try:
        sock = socket.create_connection((host, 443), timeout=timeout)
        start = time.time()
        sock.sendall(b"\x00")
        sock.recv(1)
        latency = (time.time() - start) * 1000
        sock.close()
        return round(latency, 1)
    except Exception:
        return None

class HealthMonitor:
    """健康监控."""

    def __init__(self):
        self._health_status = {}  # {platform: {"ok": bool, "last_check": float, "latency": float}}
        self._connection_health = {
            "last_check": 0,
            "check_interval": 60,
            "consecutive_failures": 0,
            "last_reconnect": 0,
            "history": [],
        }
        self._reconnect_count = 0

    async def check_health(self) -> Dict[str, Any]:
        """检查整体健康状态（含浏览器、磁盘、网络）."""
        now = time.time()
        if now - self._connection_health["last_check"] < self._connection_health["check_interval"]:
            return self._connection_health

        self._connection_health["last_check"] = now
        ok = False
        pages_count = 0
        mem_mb = 0

        if BROWSER_AGENT_AVAILABLE:
            agent = get_browser_agent()
            if agent and agent.ensure_ready():
                ok = True
                pages_count = 0
                self._connection_health["consecutive_failures"] = 0
            else:
                self._connection_health["consecutive_failures"] += 1
        else:
            self._connection_health["consecutive_failures"] += 1

        if self._connection_health["consecutive_failures"] >= 3:
            self._connection_health["last_reconnect"] = now
            self._connection_health["consecutive_failures"] = 0

        # 磁盘空间检查
        disk = _check_disk_space()
        disk_warning = disk.get("percent_used", 0) > 90 if isinstance(disk.get("percent_used"), (int, float)) else False

        # 网络延迟检查
        latency = _check_network_latency()
        network_ok = latency is not None and latency < 1000

        # 综合健康评分 (0-100)
        score = 0
        if ok:
            score += 40  # 浏览器可用
        if not disk_warning:
            score += 30  # 磁盘充足
        if network_ok:
            score += 20  # 网络正常
        if self._connection_health["consecutive_failures"] == 0:
            score += 10  # 无连续失败

        self._connection_health["health_score"] = score
        self._connection_health["disk"] = disk
        self._connection_health["network_latency_ms"] = latency

        # 记录历史
        self._connection_health["history"].append({
            "ts": now,
            "ok": ok,
            "pages": pages_count,
            "memory_mb": mem_mb,
            "disk_percent": disk.get("percent_used", 0) if isinstance(disk, dict) else 0,
            "latency_ms": latency,
            "health_score": score,
        })
        if len(self._connection_health["history"]) > 30:
            self._connection_health["history"] = self._connection_health["history"][-30:]

        return self._connection_health

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态."""
        return {
            "agent_available": BROWSER_AGENT_AVAILABLE,
            "health": self._health_status,
            "connection": self._connection_health,
        }

# 全局监控实例
monitor = HealthMonitor()

class SessionManager:
    """会话管理."""

    async def save_snapshot(self, path: str = "") -> str:
        """保存会话快照（简化版，不包含 cookies 和页面详细信息）."""
        save_path = path or self._get_default_snapshot_path()
        try:
            os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

            snapshot = {
                "ts": time.time(),
                "version": "1.0",
                "cookies": [],  # browser-harness 模式下暂不支持
                "pages": {pk: {"url": info["url"], "title": info["name"]} for pk, info in PLATFORMS.items()},
                "fetch_stats": chat_engine._fetch_stats,
                "response_times": chat_engine._response_times,
                "cache_stats": await cache_manager.get_stats(),
                "health_status": monitor._health_status,
                "error_stats": chat_engine._error_stats,
            }

            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)

            size = os.path.getsize(save_path)
            return f"快照已保存: {save_path}\n大小: {size}字节\n页面: {len(snapshot['pages'])}个\nCookies: 0条 (简化模式)"
        except Exception as e:
            return f"保存失败: {e}"

    async def restore_snapshot(self, path: str = "") -> str:
        """恢复会话快照（简化版，仅恢复统计信息）."""
        load_path = path or self._get_default_snapshot_path()
        if not os.path.exists(load_path):
            return f"快照不存在: {load_path}"

        try:
            with open(load_path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except Exception as e:
            return f"读取失败: {e}"

        # 恢复统计（不恢复 cookies）
        for k, v in snapshot.get("fetch_stats", {}).items():
            chat_engine._fetch_stats[k] = v
        for k, v in snapshot.get("response_times", {}).items():
            chat_engine._response_times[k] = v
        for k, v in snapshot.get("error_stats", {}).items():
            chat_engine._error_stats[k] = v
        if snapshot.get("health_status"):
            monitor._health_status = snapshot["health_status"]

        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(snapshot.get("ts", 0)))
        pages = len(snapshot.get("pages", {}))
        return f"快照已恢复 (保存于{ts})\n页面配置:{pages} (cookies 未恢复)"

    async def _get_cookies(self) -> list:
        """获取cookies (浏览器无关模式下返回空列表)."""
        return []

    async def _get_pages_info(self) -> Dict[str, Dict]:
        """获取页面信息 (返回配置中的平台信息)."""
        return {pk: {"url": info["url"], "title": info["name"]} for pk, info in PLATFORMS.items()}

    def _get_default_snapshot_path(self) -> str:
        """默认快照路径."""
        path = os.path.join(os.path.expanduser("~"), ".claude", "session_snapshot.json")
        return path

# 全局会话管理器
session_manager = SessionManager()
