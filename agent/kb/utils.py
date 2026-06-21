"""kb/utils.py - Shared utility functions for KB module.

Extracts repeated code from:
  - commands/graph.py + kb_web.py (graph building)
  - kb_backup.py + kb_sync.py + daemon_core.py (process management)
"""

import json
import os
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
#  Graph building (used by commands/graph.py and kb_web.py)
# ---------------------------------------------------------------------------

def build_graph_from_index(index: Dict[str, Any]) -> Dict[str, Any]:
    """Build knowledge graph nodes and edges from an index dict.

    Shared by GraphMixin.generate_graph() and kb_web.api_graph().
    """
    nodes: List[Dict] = []
    edges: List[Dict] = []

    for doc in index.get("documents", []):
        nodes.append({
            "id": doc["path"],
            "label": doc.get("title", ""),
            "type": "document",
            "group": "documents",
        })

    for concept, docs in index.get("concepts", {}).items():
        nodes.append({
            "id": f"concept:{concept}",
            "label": concept,
            "type": "concept",
            "group": "concepts",
        })
        for doc_path in docs:
            edges.append({
                "source": f"concept:{concept}",
                "target": doc_path,
                "type": "relates_to",
            })

    for entity, docs in index.get("entities", {}).items():
        nodes.append({
            "id": f"entity:{entity}",
            "label": entity,
            "type": "entity",
            "group": "entities",
        })
        for doc_path in docs[:3]:
            edges.append({
                "source": f"entity:{entity}",
                "target": doc_path,
                "type": "mentioned_in",
            })

    # Concept inter-relationships
    all_concepts = list(index.get("concepts", {}).keys())
    for i, c1 in enumerate(all_concepts):
        for c2 in all_concepts[i + 1:]:
            if c1.lower() in c2.lower() or c2.lower() in c1.lower():
                edges.append({
                    "source": f"concept:{c1}",
                    "target": f"concept:{c2}",
                    "type": "related",
                })

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
#  Daemon process management (used by daemon.py, kb_backup.py, kb_sync.py)
# ---------------------------------------------------------------------------

def is_alive(pid: int) -> bool:
    """Check if a process is alive (cross-platform)."""
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=5,
        )
        return str(pid) in result.stdout
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def kill_pid(pid: int):
    """Force-kill a process by PID (cross-platform)."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            encoding="utf-8", errors="replace",
            timeout=10,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def read_pid_file(pid_file: Path) -> Optional[int]:
    """Read a PID from a file. Returns None on failure."""
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def write_pid_file(pid_file: Path, pid: int):
    """Write a PID to a file."""
    pid_file.write_text(str(pid), encoding="utf-8")


def log_to_file(log_dir: Path, filename: str, msg: str):
    """Append a timestamped message to a log file."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    log_file = log_dir / filename
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)
