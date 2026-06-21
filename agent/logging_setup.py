"""统一日志配置模块

提供集中式日志配置，包括控制台输出和文件轮转。
所有 agent 模块应使用 get_logger() 获取 logger 实例。
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


def setup_logging(log_dir: Path = None, level: int = logging.INFO) -> logging.Logger:
    """配置全局日志系统

    Args:
        log_dir: 日志文件存放目录，默认为 .logs
        level: 日志级别，默认 INFO

    Returns:
        根 logger 实例
    """
    if log_dir is None:
        log_dir = Path(".logs")

    log_dir.mkdir(parents=True, exist_ok=True)

    # 获取根 logger
    root_logger = logging.getLogger("agent")
    root_logger.setLevel(level)

    # 避免重复添加 handler
    if root_logger.handlers:
        return root_logger

    # 控制台 handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)

    # 文件 handler (轮转)
    log_file = log_dir / "agent.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_format = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_format)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取 logger 实例

    Args:
        name: logger 名称，通常传入 __name__

    Returns:
        配置好的 logger 实例
    """
    return logging.getLogger(f"agent.{name}")
