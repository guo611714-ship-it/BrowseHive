"""Pytest root conftest: ensure evolve/ on sys.path for fixtures + module imports."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
