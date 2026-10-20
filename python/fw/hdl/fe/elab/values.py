"""Runtime values of the elaboration interpreter.

Integral values are Python ints holding the unsigned bit pattern, masked to the
width of the SV type they belong to; signedness comes from the type where it
matters (comparison, shift, extension). Two-state only: X and Z read as 0.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Obj:
    """A class instance on the elaboration heap."""

    __slots__ = ("cls", "fields", "oid")

    def __init__(self, cls, oid: int):
        self.cls = cls                  # the runtime ClassType (specialized)
        self.fields: Dict[Any, Any] = {}  # ClassPropertySymbol -> value
        self.oid = oid

    def __repr__(self) -> str:
        return f"<{self.cls.name}#{self.oid}>"


class Iface:
    """An interface instance reached through a virtual interface handle, or
    whose procedural blocks run as threads. Variables are keyed by name."""

    __slots__ = ("inst", "path", "vars")

    def __init__(self, inst, path: str):
        self.inst = inst
        self.path = path
        self.vars: Dict[str, Any] = {}

    def __repr__(self) -> str:
        return f"<iface {self.path}>"


class Event:
    """A named event: threads blocked in @(e) wake when it is triggered."""

    __slots__ = ("name",)

    def __init__(self, name: str = ""):
        self.name = name

    def __repr__(self) -> str:
        return f"<event {self.name}>"


class Opaque:
    """A handle the design only stores (std::process and the like)."""

    __slots__ = ("what",)

    def __init__(self, what: str):
        self.what = what

    def __repr__(self) -> str:
        return f"<{self.what}>"


def mask(v: int, w: int) -> int:
    return v & ((1 << w) - 1) if w > 0 else v


def to_signed(v: int, w: int) -> int:
    v = mask(v, w)
    return v - (1 << w) if w > 0 and (v >> (w - 1)) & 1 else v


def width_of(t) -> Optional[int]:
    """Bit width of an integral type, else None."""
    t = t.canonicalType
    if t.isIntegral:
        return int(t.bitWidth)
    return None


def const_to_py(cv, t=None):
    """A slang ConstantValue to an interpreter value."""
    if cv is None:
        return None
    v = cv.value
    if v is None:
        return None
    if isinstance(v, (int, float, str)):
        return v
    name = type(v).__name__
    if name == "SVInt":
        if v.hasUnknown:
            v = v.flattenUnknowns()
        w = int(v.bitWidth)
        return mask(int(v), w)
    if name == "NullValue":
        return None
    if isinstance(v, list):
        return [const_to_py(x) for x in v]
    try:
        return cv.convertToInt()
    except Exception:
        return v


def pyslang_lit_base_hex():
    import pyslang
    return pyslang.LiteralBase.Hex


def default_value(t, oid_name: str = ""):
    """The value a variable of type *t* holds before any assignment."""
    t = t.canonicalType
    if t.isIntegral:
        return 0
    if t.isString:
        return ""
    if t.isFloating:
        return 0.0
    if t.isEvent:
        return Event(oid_name)
    if t.isAssociativeArray:
        return {}
    if t.isQueue or (t.isUnpackedArray and t.isDynamicallySizedArray):
        return []
    if t.isUnpackedArray:          # fixed-size unpacked
        r = t.fixedRange
        n = abs(int(r.left) - int(r.right)) + 1
        return [default_value(t.arrayElementType) for _ in range(n)]
    if t.isUnpackedStruct:
        out: Dict[str, Any] = {}
        for m in t:
            if m.kind.name == "Field":
                out[m.name] = default_value(m.type)
        return out
    # class handles, virtual interfaces, chandles: null
    return None


def copy_value(v):
    """Value semantics for assignment: containers are copied, handles are not."""
    if isinstance(v, list):
        return [copy_value(x) for x in v]
    if isinstance(v, dict):
        return {k: copy_value(x) for k, x in v.items()}
    return v


def truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (Obj, Iface, Event, Opaque)):
        return True
    if isinstance(v, str):
        return v != ""
    return bool(v)


def fmt_sv(fmt: str, args: List[Any], scope_name: str = "") -> str:
    """A small $sformatf: %d %h %x %b %o %s %m %t %c %%, with optional 0/width."""
    out = []
    i = 0
    ai = 0
    while i < len(fmt):
        c = fmt[i]
        if c != "%":
            out.append(c)
            i += 1
            continue
        i += 1
        j = i
        while j < len(fmt) and (fmt[j].isdigit() or fmt[j] == "-"):
            j += 1
        spec = fmt[j].lower() if j < len(fmt) else ""
        i = j + 1
        if spec == "%":
            out.append("%")
            continue
        if spec == "m":
            out.append(scope_name)
            continue
        a = args[ai] if ai < len(args) else 0
        ai += 1
        if spec == "s":
            out.append(str(a) if not isinstance(a, int) else _int_to_str(a))
        elif spec == "d":
            out.append(str(a))
        elif spec in ("h", "x"):
            out.append(format(a if isinstance(a, int) else 0, "x"))
        elif spec == "b":
            out.append(format(a if isinstance(a, int) else 0, "b"))
        elif spec == "o":
            out.append(format(a if isinstance(a, int) else 0, "o"))
        elif spec == "t":
            out.append(str(a))
        elif spec == "c":
            out.append(chr(a & 0xFF) if isinstance(a, int) else str(a))
        else:
            out.append(str(a))
    return "".join(out)


def _int_to_str(v: int) -> str:
    bs = []
    while v:
        bs.append(chr(v & 0xFF))
        v >>= 8
    return "".join(reversed(bs))
