"""daemon_core.py - DEPRECATED: use daemon.py instead.

Kept for backward compatibility. All logic moved to daemon.py.
"""

from .daemon import (  # noqa: F401
    KBDaemonCore,
    HEARTBEAT_INTERVAL_SEC,
    HEARTBEAT_TIMEOUT_SEC,
    HEALTH_CHECK_INTERVAL_SEC,
    SCRIPT_DIR,
    SERVICES,
)
