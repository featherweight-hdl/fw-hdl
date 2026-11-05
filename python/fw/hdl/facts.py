"""Characterization facts: what is known about a block's interface without
looking inside it (latency, rate, capacity, combinational paths, area).

A fact is *declared* by a person, in the class's ``facts()`` method
(``fw_facts``, ``src/fw_facts.svh``) or in a sidecar file (knob
``design.facts``); *measured* by a characterization run; *generated* by a
library generator; or produced by an *engine* that built the block. The
provenance goes with the fact into its overlay (``zuspec.ir.core.results``),
and reports show it.

A fact's value names ports by their RTL names (``in_0`` for ``in[0]``). In a
sidecar a port may be written ``in[2]`` or ``in[*]`` (every element).
"""
from __future__ import annotations

import dataclasses as dc
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: Short names (SV methods, sidecar `kind:`) -> core fact kinds.
KINDS = {
    "latency": "iface.latency",
    "ii": "iface.ii",
    "throughput": "iface.throughput",
    "capacity": "iface.capacity",
    "comb_path": "iface.comb_path",
    "stall_coupling": "iface.stall_coupling",
    "registered": "iface.registered",
    "io_delay": "timing.io_delay_ps",
    "area": "area.estimate",
}

#: The value fields that name ports, per kind.
PORT_FIELDS = {
    "iface.latency": ("src", "dst"),
    "iface.ii": ("port",),
    "iface.throughput": ("port",),
    "iface.capacity": ("src", "dst"),
    "iface.comb_path": ("src", "dst"),
    "iface.stall_coupling": ("a", "b"),
    "iface.registered": ("port",),
    "timing.io_delay_ps": ("port",),
    "area.estimate": (),
}

DECLARED, MEASURED, GENERATOR, ENGINE = "declared", "measured", "generator", "engine"

SIDECAR_FORMAT = "fw-hdl.facts"


class FactsError(Exception):
    def __init__(self, msg: str, site: Any = None):
        super().__init__(msg)
        self.site = site


@dc.dataclass
class BlockFact:
    kind: str                           # a core kind (iface.latency, ...)
    value: Dict[str, Any]
    site: Any = dc.field(default=None, compare=False, repr=False)

    def to_json(self) -> dict:
        return {"kind": self.kind, "value": dict(self.value)}

    @classmethod
    def from_json(cls, d: dict) -> "BlockFact":
        return cls(d["kind"], dict(d["value"]))


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------

_ELEM = re.compile(r"^(\w+)\[(\*|\d+)\]$")


def expand_port(name: str, ports: Sequence[str]) -> List[str]:
    """``in[2]`` -> ``in_2``; ``in[*]`` -> every ``in_<k>``; a plain name as is."""
    m = _ELEM.match(name)
    if m is None:
        return [name]
    base, idx = m.groups()
    if idx != "*":
        return [f"{base}_{idx}"]
    out = [p for p in ports if re.fullmatch(rf"{re.escape(base)}_\d+", p)]
    return sorted(out, key=lambda p: int(p.rsplit("_", 1)[1]))


def expand(fact: BlockFact, ports: Sequence[str]) -> List[BlockFact]:
    """One fact per combination of the ports its wildcards stand for; every
    port it names must be one of *ports*."""
    fields = PORT_FIELDS.get(fact.kind, ())
    combos: List[Dict[str, Any]] = [dict(fact.value)]
    for f in fields:
        if f not in fact.value:
            raise FactsError(f"{fact.kind}: no {f!r}", fact.site)
        names = expand_port(str(fact.value[f]), ports)
        if not names:
            raise FactsError(f"{fact.kind}: {fact.value[f]!r} matches no port "
                             f"(ports: {list(ports)})", fact.site)
        bad = [n for n in names if n not in ports]
        if bad:
            raise FactsError(f"{fact.kind}: {bad[0]!r} is not a port (ports: {list(ports)})",
                             fact.site)
        combos = [{**c, f: n} for c in combos for n in names]
    return [BlockFact(fact.kind, c, fact.site) for c in combos]


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def latency_range(v: Mapping[str, Any]) -> Tuple[int, Optional[int]]:
    """``(lo, hi)`` cycles of an ``iface.latency`` value; ``hi`` None when unbounded."""
    if v.get("fixed") is not None:
        return int(v["fixed"]), int(v["fixed"])
    lo = v.get("min")
    hi = v.get("max")
    return (int(lo) if lo is not None else 0), (int(hi) if hi is not None else None)


def latency_value(fixed: Optional[int] = None, lo: Optional[int] = None,
                  hi: Optional[int] = None) -> Dict[str, Any]:
    if fixed is not None:
        return {"fixed": fixed}
    out = {}
    if lo is not None:
        out["min"] = lo
    if hi is not None:
        out["max"] = hi
    return out


def check_value(f: BlockFact) -> None:
    """The kind's own rules (the core kind schema checks the shape)."""
    if f.kind == "iface.latency":
        v = f.value
        if v.get("fixed") is not None and (v.get("min") is not None or v.get("max") is not None):
            raise FactsError("latency: give fixed, or min and/or max, not both", f.site)
        if v.get("fixed") is None and v.get("min") is None and v.get("max") is None:
            raise FactsError("latency: give fixed, or min and/or max", f.site)
        lo, hi = latency_range(v)
        if lo < 0 or (hi is not None and hi < lo):
            raise FactsError(f"latency: min {lo} > max {hi}" if hi is not None and hi < lo
                             else f"latency: {lo} cycles is negative", f.site)
        if v.get("fixed") is None and v.get("min") is None:
            v["min"] = 0                # max alone: at least 0 cycles


def validate(f: BlockFact) -> None:
    """The core kind's schema (``zuspec.ir.core.results``)."""
    from zuspec.ir.core.results import Fact, FactError
    from zuspec.ir.core.results.kinds import validate as core_validate
    try:
        core_validate(Fact(f.kind, "-", f.value))
    except FactError as e:
        raise FactsError(str(e).replace(" on -", ""), f.site) from None


def for_block(declared: Iterable[BlockFact], ports: Sequence[str]) -> List[dict]:
    """A block's facts as its shell entry holds them: expanded against its
    *ports*, checked, each ``{kind, value, provenance, unverified}``."""
    out = []
    for f in declared:
        for e in expand(f, ports):
            check_value(e)
            validate(e)
            out.append({"kind": e.kind, "value": dict(e.value), "provenance": DECLARED,
                        "unverified": True})
    return out


def unverified(declared: BlockFact, measured: Iterable[BlockFact]) -> bool:
    """True unless a measured fact about the same ports agrees with *declared*
    (a measured latency range lies inside the declared one)."""
    from zuspec.ir.core.results import CONFLICT_KEYS, agrees
    keys = CONFLICT_KEYS.get(declared.kind, PORT_FIELDS.get(declared.kind, ()))
    want = tuple(declared.value.get(k) for k in keys)
    return not any(m.kind == declared.kind and tuple(m.value.get(k) for k in keys) == want
                   and agrees(m.kind, m.value, declared.value) for m in measured)


# ---------------------------------------------------------------------------
# Sidecar files
# ---------------------------------------------------------------------------

def load_sidecar(path: str) -> List[Tuple[str, List[BlockFact]]]:
    """``[(class, facts)]`` from a facts file::

        format: fw-hdl.facts
        version: 1
        blocks:
          - class: my_ip
            facts:
              - {kind: latency, src: "req[*]", dst: rsp, min: 3, max: 40}
              - {kind: area, value: 18500, unit: um2, source: "datasheet rev 2"}
    """
    import yaml
    with open(path) as f:
        d = yaml.safe_load(f) or {}
    if d.get("format") != SIDECAR_FORMAT or d.get("version") != 1:
        raise FactsError(f"{path}: not an {SIDECAR_FORMAT} v1 file")
    out = []
    for b in d.get("blocks", []) or []:
        facts = []
        for e in b.get("facts", []) or []:
            e = dict(e)
            short = e.pop("kind", None)
            if short not in KINDS:
                raise FactsError(f"{path}: class {b.get('class')}: kind {short!r}; expected one "
                                 f"of {sorted(KINDS)}")
            facts.append(BlockFact(KINDS[short], e, site=path))
        out.append((str(b["class"]), facts))
    return out


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------

def overlay(block: str, ports: Mapping[str, Any], facts: Iterable[BlockFact],
            provenance: str = DECLARED, source: Optional[str] = None):
    """``(Overlay, AnchorTable)`` holding *facts* on block *block*'s anchor.
    *ports* are the block's port fields (anchored under it)."""
    import zuspec.ir.core as ir
    from zuspec.ir.core.anchor import assign_anchors
    from zuspec.ir.core.results.overlay import Overlay, OverlayHeader
    comp = ir.DataTypeComponent(name=block, super=None, fields=list(ports.values()))
    anchors = assign_anchors([comp])
    ov = Overlay(OverlayHeader(engine="fw-hdl.facts", provenance=provenance,
                               command=source,
                               scope_hashes=dict(anchors.scope_hashes)))
    for f in facts:
        ov.add(f.kind, comp.anchor, dict(f.value))
    return ov, anchors
