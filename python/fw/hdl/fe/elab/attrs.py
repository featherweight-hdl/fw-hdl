"""fw-hdl synthesis directives: the ``(* fw_* *)`` attributes.

Each directive has the targets it may sit on and a value type. The meaning of
each is in docs/methodology/timing.md (directive summary). An ``fw_*`` name
that is not in :data:`DIRECTIVES`, a directive on the wrong target, or a value
of the wrong type is an error. Attributes without the ``fw_`` prefix are other
tools' business and are ignored.

Targets:

  ``class``   a class (all its tasks)
  ``iface``   an interface class (a port's API)
              (``fw_latency_insensitive`` also goes on the class or task that
              implements an API: a binding)
  ``task``    a task or function
  ``field``   a class property
  ``loop``    a loop statement

pyslang gives a symbol's or statement's attributes through
``Compilation.getAttributes``, except a class's: those are read from its
declaration syntax.
"""
from __future__ import annotations

import dataclasses as dc
import os
from typing import Dict, FrozenSet, Optional, Tuple

import pyslang
from pyslang import ast

from .interp import ElabError

SK = ast.StatementKind


class AttrError(ElabError):
    """A malformed fw-hdl directive."""


@dc.dataclass(frozen=True)
class Directive:
    targets: FrozenSet[str]
    kind: str                                   # 'flag' | 'int' | 'str'
    choices: Tuple[str, ...] = ()               # legal 'str' values, if limited


def _d(targets: str, kind: str, choices: Tuple[str, ...] = ()) -> Directive:
    return Directive(frozenset(targets.split()), kind, choices)


DIRECTIVES: Dict[str, Directive] = {
    "fw_timed": _d("class task", "flag"),
    "fw_latency_insensitive": _d("iface class task", "flag"),
    "fw_resource": _d("field", "str", ("stall", "bypass")),
    "fw_guard": _d("field", "str"),
    "fw_storage": _d("field", "str"),
    "fw_arbitrate": _d("field", "str"),
    "fw_ii": _d("loop task", "int"),
    "fw_predict": _d("field", "str"),
    "fw_speculate": _d("loop", "flag"),
}

LOOP_KINDS = frozenset((SK.ForLoop, SK.WhileLoop, SK.DoWhileLoop, SK.ForeverLoop,
                        SK.RepeatLoop, SK.ForeachLoop))


def target_of(node) -> Optional[str]:
    """The directive target ``node`` is, or None when it takes no directives."""
    k = getattr(node, "kind", None)
    if k in LOOP_KINDS:
        return "loop"
    if k == ast.SymbolKind.ClassType or k == ast.SymbolKind.GenericClassDef:
        return "iface" if getattr(node, "isInterface", False) else "class"
    if k == ast.SymbolKind.Subroutine:
        return "task"
    if k == ast.SymbolKind.ClassProperty:
        return "field"
    return None


def _where(comp, node) -> str:
    try:
        loc = node.location
    except AttributeError:
        try:
            loc = node.sourceRange.start
        except AttributeError:
            return "?"
    sm = comp.sourceManager
    try:
        return f"{os.path.basename(sm.getFileName(loc))}:{sm.getLineNumber(loc)}"
    except Exception:                        # pragma: no cover - defensive
        return "?"


def _raw(comp, node):
    """[(name, text, const)] as written: ``text`` is the value expression's
    source (None for a bare name); ``const`` its constant value, an int,
    where pyslang evaluated one (not for a class's attributes)."""
    if target_of(node) in ("class", "iface"):
        syn = getattr(node, "syntax", None)
        out = []
        for inst in getattr(syn, "attributes", None) or ():
            for spec in inst.specs:
                v = spec.value
                out.append((spec.name.valueText, None if v is None else str(v.expr).strip(),
                            None))
        return out
    out = []
    for at in comp.getAttributes(node):
        spec = at.syntax
        v = getattr(spec, "value", None)
        cv = at.value.value if at.value is not None else None
        const = int(cv) if isinstance(cv, pyslang.SVInt) and not cv.hasUnknown else None
        out.append((at.name, None if v is None else str(v.expr).strip(), const))
    return out


def _value(comp, name: str, d: Directive, text: Optional[str], const, where: str):
    """Convert one written value to the directive's type."""
    is_str = text is not None and len(text) >= 2 and text[0] == text[-1] == '"'
    if d.kind == "flag":
        if text is None or const == 1 or text in ("1", "1'b1"):
            return True
        raise AttrError(f"{where}: {name} is a flag; write (* {name} *)")
    if text is None:
        raise AttrError(f"{where}: {name} needs a value")
    if d.kind == "str":
        if not is_str or len(text) == 2:
            raise AttrError(f"{where}: {name} takes a string")
        return _choice(name, d, text[1:-1], where)
    if is_str:
        raise AttrError(f"{where}: {name} takes a positive integer")
    n = const
    if n is None:
        try:
            n = int(text, 0)
        except ValueError:
            raise AttrError(f"{where}: {name}={text}: not a constant") from None
    return _intval(n, name, d, where)


def _choice(name: str, d: Directive, s: str, where: str) -> str:
    if d.choices and s not in d.choices:
        raise AttrError(f"{where}: {name}=\"{s}\": one of {', '.join(d.choices)}")
    return s


def _intval(n, name: str, d: Directive, where: str):
    if n is None or n < 1:
        raise AttrError(f"{where}: {name} takes a positive integer")
    return int(n)


def read_attrs(comp, node) -> Dict[str, object]:
    """The fw-hdl directives on ``node`` (a class, interface class, task,
    field or loop statement), checked. Raises :class:`AttrError`."""
    tgt = target_of(node)
    out: Dict[str, object] = {}
    raw = _raw(comp, node) if tgt is not None else []
    for name, text, const in raw:
        if not name.startswith("fw_"):
            continue
        where = _where(comp, node)
        d = DIRECTIVES.get(name)
        if d is None:
            raise AttrError(f"{where}: unknown fw-hdl directive {name}")
        if tgt not in d.targets:
            raise AttrError(f"{where}: {name} does not apply to a {tgt}; "
                            f"it goes on a {' or '.join(sorted(d.targets))}")
        out[name] = _value(comp, name, d, text, const, where)
    return out


def class_of(sub):
    """The class a method belongs to (from its ``this``), or None."""
    tv = getattr(sub, "thisVar", None)
    if tv is None:
        return None
    t = tv.type.canonicalType
    return t if t.kind == ast.SymbolKind.ClassType else None


def in_instance(sub) -> bool:
    """Whether ``sub`` is declared in an interface or module (not a class or
    package)."""
    sc = getattr(sub, "parentScope", None)
    return sc is not None and sc.containingInstance is not None
