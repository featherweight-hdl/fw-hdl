"""Puts tests/ on sys.path so every suite can ``from fw_tools import tool``."""
import sys
from pathlib import Path

_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)
