"""配置文件热更新监控"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Any

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """配置文件变更监控器"""

    def __init__(self, config_path: Path, reload_callback: Callable, check_interval: float = 5.0):
        self.config_path = Path(config_path)
        self.reload_callback = reload_callback
        self.check_interval = check_interval
        self._running = False
        self._timer: Optional[threading.Timer] = None
        self._last_mtime: float = 0
        self._last_hash: str = ""
        self._change_log: list = []

    def start(self):
        """启动监控"""
        if self._running:
            return
        self._running = True
        self._last_mtime = self._get_mtime()
        self._last_hash = self._get_hash()
        self._schedule_check()
        logger.info("配置监控已启动: %s", self.config_path)

    def stop(self):
        """停止监控"""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("配置监控已停止")

    def _schedule_check(self):
        if not self._running:
            return
        self._timer = threading.Timer(self.check_interval, self._check)
        self._timer.daemon = True
        self._timer.start()

    def _check(self):
        if not self._running:
            return
        try:
            current_mtime = self._get_mtime()
            if current_mtime != self._last_mtime:
                current_hash = self._get_hash()
                if current_hash != self._last_hash:
                    self._on_change()
                    self._last_mtime = current_mtime
                    self._last_hash = current_hash
        except Exception as e:
            logger.error("配置检查失败: %s", e)
        finally:
            self._schedule_check()

    def _get_mtime(self) -> float:
        if self.config_path.exists():
            return self.config_path.stat().st_mtime
        return 0

    def _get_hash(self) -> str:
        if self.config_path.exists():
            content = self.config_path.read_bytes()
            return str(hash(content))
        return ""

    def _on_change(self):
        """配置变更处理"""
        try:
            config = self._load_config()
            if config is not None:
                self.reload_callback(config)
                self._change_log.append({
                    "time": time.time(),
                    "path": str(self.config_path)
                })
                logger.info("配置已重新加载: %s", self.config_path)
        except Exception as e:
            logger.error("配置重新加载失败: %s", e)

    def _load_config(self) -> Optional[Dict[str, Any]]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def get_change_log(self) -> list:
        return list(self._change_log)


# 便捷函数
def watch_config(config_path: Path, reload_callback: Callable, check_interval: float = 5.0) -> ConfigWatcher:
    watcher = ConfigWatcher(config_path, reload_callback, check_interval)
    watcher.start()
    return watcher
