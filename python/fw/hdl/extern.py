"""Wrapped IP: an existing Verilog module behind an fw-hdl class.

A class that implements ``fw_extern_impl`` (``src/fw_extern.svh``) says, in
``extern_map()``, which module realizes it, with which parameter values, and
which module pins each of its ports is. The elaborator runs ``extern_map()``
and records the result as an :class:`ExternRecord`. Partition then reads the
module's header with those parameter values (:mod:`fw.hdl.rtl_header`),
checks that every pin is accounted for exactly once and has the width and
direction its port implies (:func:`check`), and derives the block signature
Integrate wires it by (:func:`signature`). Nobody writes the signature.

A record is a function of the class and its parameter object: two instances
of one specialization must give the same record (Partition checks).
"""
from __future__ import annotations

import dataclasses as dc
import os
import shlex
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import zuspec.ir.core as ir

from .rtl_header import Header, HeaderError, read_header

Value = Union[int, str]

KINDS = ("rv", "valid", "level")
STYLES = ("fw", "xls")

#: Pin templates of the endpoint kinds that have no kit (``${ep}`` is the
#: endpoint name the map gives). A ready/valid endpoint uses the ``fw_rv``
#: kit's template.
_VALID_PINS = {"fw": {"data": "${ep}", "valid": "${ep}_valid"},
               "xls": {"data": "${ep}", "valid": "${ep}_vld"}}


class ExternError(Exception):
    """A wrapped module's map is wrong. ``site`` is the SV syntax to point
    at (the map call, or the class)."""

    def __init__(self, msg: str, site: Any = None):
        super().__init__(msg)
        self.site = site


@dc.dataclass
class Binding:
    """One class port bound to a group of module pins."""
    port: str                   # the port's RTL name (``in_0`` for ``in[0]``)
    kind: str                   # rv | valid | level
    name: str                   # the endpoint name in pin templates
    style: str = "fw"
    pins: Dict[str, str] = dc.field(default_factory=dict)   # role -> pin, overriding
    site: Any = dc.field(default=None, compare=False, repr=False)

    def to_json(self) -> dict:
        return {"port": self.port, "kind": self.kind, "name": self.name,
                "style": self.style, "pins": dict(self.pins)}


@dc.dataclass
class ExternRecord:
    """What one wrapper's ``extern_map()`` said."""
    cls: str                    # the wrapper class, as SV spells it
    module: str
    fileset: str                # as written in `fw_extern_utils
    params: Dict[str, Value] = dc.field(default_factory=dict)
    clock: str = ""
    reset: str = ""
    reset_active_low: bool = False
    bindings: List[Binding] = dc.field(default_factory=list)
    ties: List[Tuple[str, int]] = dc.field(default_factory=list)
    opens: List[str] = dc.field(default_factory=list)
    #: Where each pin was named, for diagnostics (not part of the record).
    sites: Dict[str, Any] = dc.field(default_factory=dict, compare=False, repr=False)
    site: Any = dc.field(default=None, compare=False, repr=False)

    FORMAT = "fw-hdl.extern-record"
    VERSION = 1

    def to_json(self) -> dict:
        return {"format": self.FORMAT, "version": self.VERSION, "class": self.cls,
                "module": self.module, "fileset": self.fileset, "params": dict(self.params),
                "clock": self.clock, "reset": self.reset,
                "reset_active_low": self.reset_active_low,
                "bindings": [b.to_json() for b in self.bindings],
                "ties": [list(t) for t in self.ties], "opens": list(self.opens)}

    @classmethod
    def from_json(cls, d: dict) -> "ExternRecord":
        if d.get("format") != cls.FORMAT or d.get("version") != cls.VERSION:
            raise ValueError(f"not an {cls.FORMAT} v{cls.VERSION} record")
        return cls(cls=d["class"], module=d["module"], fileset=d["fileset"],
                   params=dict(d["params"]), clock=d["clock"], reset=d["reset"],
                   reset_active_low=bool(d["reset_active_low"]),
                   bindings=[Binding(**b) for b in d["bindings"]],
                   ties=[(p, int(v)) for p, v in d["ties"]], opens=list(d["opens"]))


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def files(rec: ExternRecord, decl_file: Optional[str],
          filesets: Optional[Mapping[str, Sequence[str]]] = None) -> List[str]:
    """The module's source files. The fileset string names a fileset (knob
    ``design.filesets``), or lists paths, relative to *decl_file*'s directory."""
    fs = rec.fileset.strip()
    if filesets and fs in filesets:
        return [str(f) for f in filesets[fs]]
    if not fs:
        raise ExternError(f"{rec.cls}: extern_fileset() is empty", rec.site)
    base = os.path.dirname(os.path.abspath(decl_file)) if decl_file else os.getcwd()
    out = []
    for f in shlex.split(fs):
        p = f if os.path.isabs(f) else os.path.normpath(os.path.join(base, f))
        if not os.path.isfile(p):
            known = f"; filesets: {sorted(filesets)}" if filesets else ""
            raise ExternError(f"{rec.cls}: extern_fileset() {fs!r}: no file {p}{known}",
                              rec.site)
        out.append(p)
    return out


def header(rec: ExternRecord, srcs: Sequence[str]) -> Header:
    try:
        return read_header(srcs, rec.module, rec.params)
    except HeaderError as e:
        raise ExternError(f"{rec.cls}: {e}", rec.site) from None


# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------

def _fw_rv_transactor():
    from . import kits
    kit = kits.registry().kits["fw_rv"]
    return next(t for t in kit.transactors if t.endpoint == "port")


def pins_of(b: Binding) -> Dict[str, str]:
    """role -> module pin, for one binding."""
    from string import Template
    if b.kind == "level":
        return {"data": b.pins["data"]}
    if b.style not in STYLES:
        raise ExternError(f"port {b.port}: pin style {b.style!r}; expected one of "
                          f"{list(STYLES)}", b.site)
    if b.kind == "rv":
        from zuspec.synth.kits.registry import KitError, pin_names
        try:
            return pin_names(_fw_rv_transactor(), b.name, b.style, b.pins)
        except KitError as e:
            raise ExternError(f"port {b.port}: {e}", b.site) from None
    out = {r: Template(t).substitute(ep=b.name) for r, t in _VALID_PINS[b.style].items()}
    out.update(b.pins)
    return out


def _flow(port: ir.Field) -> str:
    return port.pragmas.get("fw_flow", "ready_valid")


def _dir(port: ir.Field) -> str:
    return "in" if isinstance(port.datatype, ir.DataTypeGetIF) else "out"


#: The direction of each role's pin on the module, by the port's direction.
_ROLE_DIR = {"in": {"data": "in", "valid": "in", "ready": "out"},
             "out": {"data": "out", "valid": "out", "ready": "in"}}

_KIND_FLOW = {"rv": "ready_valid", "valid": "valid", "level": "level"}


def check(rec: ExternRecord, hdr: Header, ports: Mapping[str, ir.Field]) -> None:
    """Every module pin is accounted for exactly once (a port's pin, the
    clock or reset, a tie or an open), with the width and direction its use
    implies; every class port is bound once."""
    used: Dict[str, str] = {}

    def claim(pin: str, what: str, site) -> None:
        if pin in used:
            raise ExternError(f"{rec.cls}: pin {pin!r} of {rec.module} is both {used[pin]} "
                              f"and {what}", site)
        hp = hdr.port(pin)
        if hp is None:
            raise ExternError(f"{rec.cls}: {what}: {rec.module} has no pin {pin!r} "
                              f"(pins: {[p.name for p in hdr.ports]})", site)
        used[pin] = what

    def expect(pin: str, direction: str, width: int, what: str, site) -> None:
        hp = hdr.port(pin)
        if hp.direction != direction:
            raise ExternError(f"{rec.cls}: {what}: pin {pin!r} of {rec.module} is an "
                              f"{_dir_word(hp.direction)}, expected an {_dir_word(direction)}",
                              site)
        if width and hp.width != width:
            raise ExternError(f"{rec.cls}: {what}: pin {pin!r} of {rec.module} is "
                              f"{hp.width} bits with {_params(rec)}, expected {width}", site)

    if not rec.clock:
        raise ExternError(f"{rec.cls}: extern_map() names no clock pin (x.clock(...))", rec.site)
    for pin, what, s in ((rec.clock, "the clock", rec.sites.get("clock")),
                         (rec.reset, "the reset", rec.sites.get("reset"))):
        if pin:
            claim(pin, what, s)
            expect(pin, "in", 1, what, s)

    bound: Dict[str, Binding] = {}
    for b in rec.bindings:
        port = ports.get(b.port)
        if port is None:
            raise ExternError(f"{rec.cls}: x.{b.kind}(...) names a port that is not one of "
                              f"its own ({sorted(ports)})", b.site)
        if b.port in bound:
            raise ExternError(f"{rec.cls}: port {b.port} is mapped twice", b.site)
        bound[b.port] = b
        flow, d = _flow(port), _dir(port)
        if _KIND_FLOW[b.kind] != flow:
            raise ExternError(f"{rec.cls}: port {b.port} is a {flow.replace('_', '/')} port; "
                              f"map it with x.{_kind_for(flow)}(...), not x.{b.kind}(...)",
                              b.site)
        if b.kind == "valid" and d != "out":
            raise ExternError(f"{rec.cls}: port {b.port}: x.valid(...) maps a valid-only "
                              f"output; a receiving port has a ready", b.site)
        bits = port.datatype.element_type.bits
        for role, pin in pins_of(b).items():
            what = f"port {b.port} {role}"
            claim(pin, what, b.site)
            pdir = "in" if b.kind == "level" and d == "in" else \
                "out" if b.kind == "level" else _ROLE_DIR[d][role]
            expect(pin, pdir, bits if role == "data" else 1, what, b.site)
    missing = [p for p in ports if p not in bound]
    if missing:
        raise ExternError(f"{rec.cls}: extern_map() does not map port(s) {missing}", rec.site)

    for pin, value in rec.ties:
        s = rec.sites.get(f"tie:{pin}")
        claim(pin, "a tie", s)
        hp = hdr.port(pin)
        if hp.direction != "in":
            raise ExternError(f"{rec.cls}: x.tie({pin!r}, ...): an {_dir_word(hp.direction)} "
                              f"cannot be tied; x.open() leaves an output unconnected", s)
        if value < 0 or value >= (1 << hp.width):
            raise ExternError(f"{rec.cls}: x.tie({pin!r}, {value}): does not fit "
                              f"{hp.width} bits", s)
    for pin in rec.opens:
        s = rec.sites.get(f"open:{pin}")
        claim(pin, "open", s)
        hp = hdr.port(pin)
        if hp.direction != "out":
            raise ExternError(f"{rec.cls}: x.open({pin!r}): an {_dir_word(hp.direction)} "
                              f"cannot be left open; tie it (x.tie)", s)
    rest = [p.name for p in hdr.ports if p.name not in used]
    if rest:
        raise ExternError(f"{rec.cls}: pin(s) {rest} of {rec.module} are not accounted for; "
                          f"map each to a port, the clock or reset, x.tie() an input, or "
                          f"x.open() an output", rec.site)


def _kind_for(flow: str) -> str:
    return {v: k for k, v in _KIND_FLOW.items()}[flow]


def _dir_word(d: str) -> str:
    return {"in": "input", "out": "output"}.get(d, d)


def _params(rec: ExternRecord) -> str:
    return ("parameters " + ", ".join(f"{k}={v}" for k, v in rec.params.items())) \
        if rec.params else "default parameters"


# ---------------------------------------------------------------------------
# Signature and instance
# ---------------------------------------------------------------------------

def signature(rec: ExternRecord, ports: Mapping[str, ir.Field],
              srcs: Sequence[str]) -> ir.BlockSignature:
    """The block signature of the wrapped module (after :func:`check`)."""
    chans = []
    by_port = {b.port: b for b in rec.bindings}
    for name, port in ports.items():
        b = by_port[name]
        flow = {"rv": "ready_valid", "valid": "valid", "level": "none"}[b.kind]
        chans.append(ir.ChannelSignature(name=name, direction=_dir(port),
                                         payload=port.datatype.element_type,
                                         flow_control=flow, ports=pins_of(b),
                                         payload_sv_type=port.pragmas.get("sv_type")))
    return ir.BlockSignature(name=rec.module, kind="proc", channels=chans, clock=rec.clock,
                             reset=rec.reset or None, reset_active_low=rec.reset_active_low,
                             engine="extern", sources=list(srcs))


def literal(v: Value) -> str:
    """A parameter value as Verilog."""
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    return '"' + str(v).replace('"', '\\"') + '"'


def instance_extras(rec: ExternRecord, hdr: Header) -> dict:
    """What Integrate adds to the instance beyond the signature's channels:
    parameters (as Verilog), ties (pin -> constant) and opens."""
    widths = {p.name: p.width for p in hdr.ports}
    return {"params": {k: literal(v) for k, v in rec.params.items()},
            "ties": {p: f"{widths[p]}'d{v}" for p, v in rec.ties},
            "opens": list(rec.opens)}
