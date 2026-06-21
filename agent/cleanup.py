"""自动数据清理模块

提供内存存档、日志文件的定时清理功能
"""

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def cleanup_memory_archives(memory_dir: Path, retention_days: int = 90) -> Dict[str, int]:
    """清理 memory_dir/archive/ 下超过 retention_days 的 .jsonl 文件

    Args:
        memory_dir: 内存数据目录
        retention_days: 保留天数，默认90天

    Returns:
        清理统计信息 dict，包含 deleted_count 和 errors
    """
    stats = {"deleted_count": 0, "errors": 0}
    archive_dir = memory_dir / "archive"
    versions_dir = memory_dir / "versions"

    cutoff_time = time.time() - (retention_days * 24 * 3600)

    # 清理 archive/ 下的 .jsonl 文件
    if archive_dir.exists():
        try:
            for file_path in archive_dir.glob("*.jsonl"):
                try:
                    if file_path.is_file():
                        if os.path.getmtime(file_path) < cutoff_time:
                            file_path.unlink()
                            stats["deleted_count"] += 1
                except FileNotFoundError:
                    pass  # 文件被并发删除，忽略
                except Exception as e:
                    stats["errors"] += 1
                    logger.debug("清理archive文件失败 %s: %s", file_path, e)
        except Exception as e:
            stats["errors"] += 1
            logger.warning("遍历archive目录失败: %s", e)

    # 清理 versions/ 下的 .snapshot.md 文件
    if versions_dir.exists():
        try:
            for file_path in versions_dir.rglob("*.snapshot.md"):
                try:
                    if file_path.is_file():
                        if os.path.getmtime(file_path) < cutoff_time:
                            file_path.unlink()
                            stats["deleted_count"] += 1
                except FileNotFoundError:
                    pass  # 文件被并发删除，忽略
                except Exception as e:
                    stats["errors"] += 1
                    logger.debug("清理snapshot文件失败 %s: %s", file_path, e)
        except Exception as e:
            stats["errors"] += 1
            logger.warning("遍历versions目录失败: %s", e)

    return stats


def cleanup_old_logs(log_dir: Path, retention_days: int = 30) -> Dict[str, int]:
    """清理 log_dir 下超过 retention_days 的 .log 文件

    Args:
        log_dir: 日志目录
        retention_days: 保留天数，默认30天

    Returns:
        清理统计信息 dict
    """
    stats = {"deleted_count": 0, "errors": 0}

    if not log_dir.exists():
        return stats

    cutoff_time = time.time() - (retention_days * 24 * 3600)

    try:
        for file_path in log_dir.glob("*.log"):
            try:
                if file_path.is_file():
                    if os.path.getmtime(file_path) < cutoff_time:
                        file_path.unlink()
                        stats["deleted_count"] += 1
            except FileNotFoundError:
                pass
            except Exception as e:
                stats["errors"] += 1
                logger.debug("清理日志文件失败 %s: %s", file_path, e)
    except Exception as e:
        stats["errors"] += 1
        logger.warning("遍历日志目录失败: %s", e)

    return stats


def cleanup_all(data_dir: Optional[Path] = None, log_dir: Optional[Path] = None) -> Dict[str, int]:
    """统一清理入口

    Args:
        data_dir: 数据目录，默认使用config.DATA_DIR
        log_dir: 日志目录，默认 .logs

    Returns:
        合并后的清理统计信息 dict
    """
    if data_dir is None:
        try:
            from .config import DATA_DIR
            data_dir = DATA_DIR
        except ImportError:
            data_dir = Path(".team")
    if log_dir is None:
        log_dir = Path(".logs")

    stats = {"deleted_count": 0, "errors": 0}

    # 清理内存存档
    try:
        archive_stats = cleanup_memory_archives(data_dir)
        stats["deleted_count"] += archive_stats["deleted_count"]
        stats["errors"] += archive_stats["errors"]
    except Exception as e:
        stats["errors"] += 1
        logger.error("清理内存存档失败: %s", e)

    # 清理旧日志
    try:
        log_stats = cleanup_old_logs(log_dir)
        stats["deleted_count"] += log_stats["deleted_count"]
        stats["errors"] += log_stats["errors"]
    except Exception as e:
        stats["errors"] += 1
        logger.error("清理旧日志失败: %s", e)

    return stats


class CleanupScheduler:
    """定时清理调度器（可取消）"""

    def __init__(self, interval_hours: int = 24):
        self.interval_hours = interval_hours
        self._timer: Optional[threading.Timer] = None
        self._running = False

    def start(self):
        """启动调度器"""
        self._running = True
        self._schedule_next()

    def stop(self):
        """停止调度器"""
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _schedule_next(self):
        """调度下一次清理"""
        if not self._running:
            return
        self._timer = threading.Timer(self.interval_hours * 3600, self._run_cleanup)
        self._timer.daemon = True
        self._timer.start()

    def _run_cleanup(self):
        """执行清理任务"""
        if not self._running:
            return
        try:
            cleanup_all()
        except Exception as e:
            logger.error("定时清理失败: %s", e)
        # 调度下一次
        self._schedule_next()


def start_cleanup_scheduler(interval_hours: int = 24) -> CleanupScheduler:
    """启动定时清理调度器

    Args:
        interval_hours: 清理间隔（小时），默认24小时

    Returns:
        CleanupScheduler 对象，可调用 stop() 取消
    """
    scheduler = CleanupScheduler(interval_hours)
    scheduler.start()
    return scheduler
