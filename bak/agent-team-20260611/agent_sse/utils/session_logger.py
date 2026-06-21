"""Session-aware logger with rate limiting, truncation, and sensitive info sanitization."""

import re
import time
from collections import defaultdict
from logging.handlers import TimedRotatingFileHandler
import logging
import os


class SessionLogger:
    """Per-session logger with rate limiting and sensitive info sanitization."""

    SENSITIVE_PATTERNS = [
        (re.compile(r'(password|passwd|pwd)\s*[=:]\s*\S+', re.IGNORECASE), r'\1=***'),
        (re.compile(r'(api_key|apikey|api-key)\s*[=:]\s*\S+', re.IGNORECASE), r'\1=***'),
        (re.compile(r'(secret|token)\s*[=:]\s*\S+', re.IGNORECASE), r'\1=***'),
        (re.compile(r'\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b'), '***'),
        (re.compile(r'-----BEGIN .*? PRIVATE KEY-----.*?-----END .*? PRIVATE KEY-----', re.DOTALL), '***'),
        (re.compile(r'\b\d{17}[\dXx]\b'), '***'),
        (re.compile(r'\b1[3-9]\d{9}\b'), '***'),
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'), '***'),
    ]

    def __init__(self, max_per_second: int = 100, log_dir: str = 'logs'):
        self.max_per_second = max_per_second
        self._counts: dict[str, list[float]] = defaultdict(list)
        self._logger = self._setup_logger(log_dir)

    def _setup_logger(self, log_dir: str) -> logging.Logger:
        # Use unique logger name per log_dir to avoid singleton handler conflicts
        logger_name = f'session_logger.{log_dir}'
        logger = logging.getLogger(logger_name)
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            os.makedirs(log_dir, exist_ok=True)
            handler = TimedRotatingFileHandler(
                os.path.join(log_dir, 'session.log'),
                when='midnight',
                backupCount=7,
                encoding='utf-8',
            )
            handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
            logger.addHandler(handler)
        return logger

    def sanitize(self, text: str) -> str:
        result = text
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    def truncate(self, text: str, max_len: int = 100) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."

    def should_log(self, session_id: str) -> bool:
        now = time.time()
        existing = self._counts.get(session_id, [])
        timestamps = [t for t in existing if now - t < 1.0]
        if not timestamps:
            if session_id in self._counts:
                del self._counts[session_id]
            self._counts[session_id] = [now]
            return True
        if len(timestamps) >= self.max_per_second:
            self._counts[session_id] = timestamps
            return False
        self._counts[session_id] = timestamps + [now]
        return True

    def log_session(self, session_id: str, trace_id: str, message: str):
        if not self.should_log(session_id):
            return
        sanitized = self.sanitize(self.truncate(message))
        self._logger.info(f"[SESSION] session={session_id} trace={trace_id} message={sanitized}")
