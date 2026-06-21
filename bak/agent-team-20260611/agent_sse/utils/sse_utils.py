import json
from typing import Any


def format_sse_event(data: Any, event_type: str = None) -> str:
    lines = []
    if event_type:
        lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def sse_done() -> str:
    return "data: [DONE]\n\n"


def sse_heartbeat() -> str:
    return ": heartbeat\n\n"
