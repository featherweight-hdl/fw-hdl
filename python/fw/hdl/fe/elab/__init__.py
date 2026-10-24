"""Elaborate-then-lower front end (docs: fw-i2c docs/design/synthesis-plan.md §0)."""
from .entry import ElabResult, elaborate
from .interp import ElabError

__all__ = ["ElabResult", "ElabError", "elaborate"]
