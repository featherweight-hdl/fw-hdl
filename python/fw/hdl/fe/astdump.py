"""Minimal AST dump for ``fw-hdl sv2ir`` at P0.

Walks the elaborated design and prints the user (non-library) component classes
and their members.  This is a parsing-sanity view; the real SPL-IR mapping
arrives at P1.
"""
from __future__ import annotations

import sys
from typing import List, Optional

from pyslang import ast

# Library class name prefixes to skip when listing the *design*.
_LIB_PREFIXES = ("fw_", "zsp_")


def is_user_class(sym) -> bool:
    """True for a user-defined class (not fw-hdl/zsp library, not a specialization)."""
    if sym.kind != ast.SymbolKind.ClassType:
        return False
    try:
        name = sym.name
    except UnicodeDecodeError:  # pragma: no cover - mangled internal symbol
        return False
    if not isinstance(name, str) or not name:
        return False
    if name.startswith(_LIB_PREFIXES):
        return False
    if getattr(sym, "genericClass", None) is not None:
        return False
    return True


def collect_user_classes(root) -> List[object]:
    found: List[object] = []

    def visit(sym):
        if is_user_class(sym):
            found.append(sym)
        return True

    root.visit(visit)
    return found


def dump(root, *, top: Optional[str] = None, out=sys.stdout) -> None:
    classes = collect_user_classes(root)
    if top is not None:
        classes = [c for c in classes if c.name == top]
        if not classes:
            print(f"; top class {top!r} not found", file=out)
            return

    for cls in classes:
        print(f"class {cls.name}", file=out)
        for member in cls:
            kind = getattr(member, "kind", "?")
            kind_name = getattr(kind, "name", str(kind))
            name = getattr(member, "name", "?")
            print(f"  {kind_name}: {name}", file=out)
