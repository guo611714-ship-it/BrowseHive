"""cleanup模块测试"""

import os
import time
import threading
from pathlib import Path

import pytest
from agent.cleanup import (
    cleanup_memory_archives,
    cleanup_old_logs,
    cleanup_all,
    start_cleanup_scheduler,
    CleanupScheduler,
)


class TestCleanupMemoryArchives:
    def test_no_archive_dir(self, tmp_path):
        """archive目录不存在时返回空统计"""
        stats = cleanup_memory_archives(tmp_path)
        assert stats["deleted_count"] == 0
        assert stats["errors"] == 0

    def test_deletes_old_files(self, tmp_path):
        """删除超过保留期的文件"""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        old_file = archive_dir / "old.jsonl"
        old_file.write_text("old data")
        old_time = time.time() - 91 * 86400
        os.utime(old_file, (old_time, old_time))

        stats = cleanup_memory_archives(tmp_path, retention_days=90)
        assert stats["deleted_count"] == 1
        assert not old_file.exists()

    def test_keeps_recent_files(self, tmp_path):
        """保留近期文件"""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()
        new_file = archive_dir / "new.jsonl"
        new_file.write_text("new data")

        stats = cleanup_memory_archives(tmp_path, retention_days=90)
        assert stats["deleted_count"] == 0
        assert new_file.exists()

    def test_cleans_versions(self, tmp_path):
        """清理versions目录下的旧快照"""
        versions_dir = tmp_path / "versions"
        versions_dir.mkdir(parents=True)
        old_snap = versions_dir / "old.snapshot.md"
        old_snap.write_text("old snapshot")
        old_time = time.time() - 100 * 86400
        os.utime(old_snap, (old_time, old_time))

        stats = cleanup_memory_archives(tmp_path, retention_days=90)
        assert stats["deleted_count"] == 1
        assert not old_snap.exists()


class TestCleanupOldLogs:
    def test_no_log_dir(self, tmp_path):
        """日志目录不存在时返回空统计"""
        stats = cleanup_old_logs(tmp_path / "nonexistent")
        assert stats["deleted_count"] == 0

    def test_deletes_old_logs(self, tmp_path):
        """删除旧日志文件"""
        old_log = tmp_path / "old.log"
        old_log.write_text("old log")
        old_time = time.time() - 31 * 86400
        os.utime(old_log, (old_time, old_time))

        stats = cleanup_old_logs(tmp_path, retention_days=30)
        assert stats["deleted_count"] == 1
        assert not old_log.exists()

    def test_keeps_recent_logs(self, tmp_path):
        """保留近期日志"""
        new_log = tmp_path / "new.log"
        new_log.write_text("new log")

        stats = cleanup_old_logs(tmp_path, retention_days=30)
        assert stats["deleted_count"] == 0
        assert new_log.exists()


class TestCleanupAll:
    def test_default_dirs(self):
        """默认目录不报错"""
        stats = cleanup_all()
        assert "deleted_count" in stats
        assert "errors" in stats

    def test_custom_dirs(self, tmp_path):
        """自定义目录"""
        data_dir = tmp_path / "data"
        log_dir = tmp_path / "logs"
        data_dir.mkdir()
        log_dir.mkdir()

        stats = cleanup_all(data_dir=data_dir, log_dir=log_dir)
        assert stats["deleted_count"] == 0
        assert stats["errors"] == 0


class TestStartCleanupScheduler:
    def test_returns_scheduler(self):
        """返回CleanupScheduler对象"""
        scheduler = start_cleanup_scheduler(interval_hours=24)
        assert isinstance(scheduler, CleanupScheduler)
        scheduler.stop()

    def test_can_be_stopped(self):
        """可以停止调度"""
        scheduler = start_cleanup_scheduler(interval_hours=24)
        scheduler.stop()
        assert scheduler._running is False
