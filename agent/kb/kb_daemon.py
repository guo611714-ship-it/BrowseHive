"""kb_daemon.py - DEPRECATED: use daemon.py instead.

Kept for backward compatibility. All logic moved to daemon.py.
"""

from .daemon import (  # noqa: F401
    KBDaemonManager,
    heartbeat_writer,
    main,
)
