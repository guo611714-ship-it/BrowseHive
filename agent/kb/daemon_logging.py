"""daemon_logging.py - DEPRECATED: use daemon.py instead.

Kept for backward compatibility. All logic moved to daemon.py.
"""

from .daemon import (  # noqa: F401
    log_info,
    log_ok,
    log_warn,
    log_err,
    log_start,
    log_stop,
)
