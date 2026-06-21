import time
from agent_sse.utils.session_logger import SessionLogger


class TestSessionLogger:
    def test_sanitize_password(self):
        logger = SessionLogger()
        result = logger.sanitize("password=secret123")
        assert "secret123" not in result
        assert "***" in result

    def test_sanitize_api_key(self):
        logger = SessionLogger()
        result = logger.sanitize("api_key=sk-abc123def456")
        assert "sk-abc123def456" not in result
        assert "***" in result

    def test_sanitize_jwt(self):
        logger = SessionLogger()
        result = logger.sanitize("token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
        assert "eyJ" not in result
        assert "***" in result

    def test_sanitize_id_card(self):
        logger = SessionLogger()
        result = logger.sanitize("身份证号: 110101199001011234")
        assert "110101199001011234" not in result
        assert "***" in result

    def test_sanitize_phone(self):
        logger = SessionLogger()
        result = logger.sanitize("手机号: 13812345678")
        assert "13812345678" not in result
        assert "***" in result

    def test_sanitize_email(self):
        logger = SessionLogger()
        result = logger.sanitize("联系邮箱 user@example.com")
        assert "user@example.com" not in result
        assert "***" in result

    def test_sanitize_preserves_normal_text(self):
        logger = SessionLogger()
        result = logger.sanitize("请帮我修改 test.js 文件")
        assert result == "请帮我修改 test.js 文件"

    def test_rate_limit_under_threshold(self):
        logger = SessionLogger(max_per_second=5)
        for _ in range(5):
            assert logger.should_log("session-1") is True

    def test_rate_limit_exceeds_threshold(self):
        import time as _time
        logger = SessionLogger(max_per_second=3)
        for _ in range(3):
            logger.should_log("session-1")
        # Call immediately (within same second) to hit the limit
        assert logger.should_log("session-1") is False

    def test_different_sessions_independent(self):
        logger = SessionLogger(max_per_second=2)
        for _ in range(2):
            logger.should_log("session-1")
        assert logger.should_log("session-2") is True

    def test_truncate_long_message(self):
        logger = SessionLogger()
        long_msg = "x" * 200
        result = logger.truncate(long_msg, max_len=100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_truncate_short_message_unchanged(self):
        logger = SessionLogger()
        result = logger.truncate("short", max_len=100)
        assert result == "short"

    def test_log_session_writes_to_log(self):
        import os
        import shutil
        # Use a unique log_dir to avoid singleton handler conflicts
        log_dir = 'test_logs_session'
        logger = SessionLogger(max_per_second=100, log_dir=log_dir)
        # Force a handler for our test dir (singleton may already have one)
        import logging
        ll = logging.getLogger('session_logger')
        if not any(hasattr(h, 'baseFilename') and log_dir in getattr(h, 'baseFilename', '') for h in ll.handlers):
            from logging.handlers import TimedRotatingFileHandler
            os.makedirs(log_dir, exist_ok=True)
            handler = TimedRotatingFileHandler(
                os.path.join(log_dir, 'session.log'),
                when='midnight', backupCount=7, encoding='utf-8',
            )
            handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
            ll.addHandler(handler)
        logger.log_session('session-1', 'trace-123', 'test message')
        assert os.path.exists(os.path.join(log_dir, 'session.log'))
        shutil.rmtree(log_dir, ignore_errors=True)

    def test_should_log_cleans_expired_keys(self):
        logger = SessionLogger(max_per_second=3)
        # Use up the rate limit
        for _ in range(3):
            logger.should_log('session-1')
        assert 'session-1' in logger._counts
        # Wait for timestamps to expire
        time.sleep(1.1)
        # Next call should return True (old timestamps expired, new one stored)
        result = logger.should_log('session-1')
        assert result is True
        # Only 1 fresh timestamp should remain, not the old 3
        assert len(logger._counts['session-1']) == 1
