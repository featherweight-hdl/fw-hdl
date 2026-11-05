"""Storage binding: the knob ``storage:`` picks what holds each channel's
values, without a change to the source (docs/methodology/storage.md).

The source names an ``fw_channel #(T, DEPTH)``; :func:`plan` resolves each
channel's binding from the knob and writes it on the partition, where
Integrate (a channel between blocks) and the group's codegen (a channel
inside an ``island.groups`` group) read it:

==========  =================================  ===================================
bind        between blocks                     inside a group
==========  =================================  ===================================
flops       ``fw_rv_fifo``                     ``--fifo_module=fw_xls_fifo_wrapper``
wrapper     ``module:``, with fw_rv_fifo's     ``--fifo_module=<module>``, with
            ports and parameters               XLS's FIFO ports
xls_fifo    (error: no XLS package holds it)   ``--materialize_internal_fifos``
sram        ``fw_sram_fifo`` and the RAM       (error: XLS's FIFO module has no
            ``macro:`` (``fw_ram_1r1w_model``) RAM ports)
==========  =================================  ===================================

Every binding has fw_rv_fifo's handshake, cycle for cycle (an SRAM FIFO
keeps its head in flops), so the class model, the contracts and the latency
report do not depend on it.

A memory member of a step class (``fw_sp_mem``,
:class:`~fw.hdl.lib.registry.MemoryKind`) is a RAM beside its block, on the
block's ``<mem>_req`` and ``<mem>_rd`` ports. Integrate places it:

==========  ===========================================================
bind        module
==========  ===========================================================
flops       ``fw_ram_1rw_model`` (a flop array)
sram        ``macro:`` (default ``fw_ram_1rw_model``), a shim with its ports
wrapper     ``module:``, with its ports
==========  ===========================================================

Every one has a 1-cycle read, the memory's own timing.

A knob key is the instance path below the top: ``q``, or ``sub.q`` for a
channel inside child ``sub``; ``u.mem`` for memory ``mem`` of child ``u``.
A table (a class with :class:`~fw.hdl.lib.registry.StorageKind`) may be
named too, but allows flops only. ``default`` applies to every channel that
holds values (DEPTH of 1 or more; a level holds none) and to every memory.
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional, Tuple

from .lib import registry as librg
from .xls_flow import XlsFlowError

#: The FIFO module per binding, between blocks.
FIFO_MODULES = {"flops": "fw_rv_fifo", "sram": "fw_sram_fifo"}
#: The RAM an SRAM FIFO uses when the knob names no ``macro:``.
RAM_MODEL = "fw_ram_1r1w_model"
#: The single-port RAM of a memory member bound to flops, or to sram with
#: no ``macro:``.
RAM_1RW_MODEL = "fw_ram_1rw_model"
#: The codegen flags of a group whose channels are bound to flops.
GROUP_FLOPS_FLAGS = ["--multi_proc", "--fifo_module=fw_xls_fifo_wrapper"]
#: The smallest DEPTH an SRAM FIFO takes (its output stage is two flops).
SRAM_MIN_DEPTH = 3

REPORT_FORMAT = "fw-hdl.storage"


def _walk(shell, prefix: str = "") -> Iterator[Tuple[str, object]]:
    """(path prefix, shell) for *shell* and every nested one."""
    yield prefix, shell
    for c in shell.children:
        if c.get("engine") == "structural":
            yield from _walk(shell.nested(c), f"{prefix}{c['name']}.")


def _channels(shell) -> Iterator[Tuple[str, dict, Optional[str]]]:
    """(path, channel dict, group) for every channel, at any depth,
    including those inside a group (group is then the group's name)."""
    for prefix, sh in _walk(shell):
        for c in sh.channels:
            yield prefix + c["name"], c, None
        for ch in sh.children:
            for c in (ch.get("group") or {}).get("internal", []):
                yield prefix + c["name"], c, ch["name"]


def _holders(shell) -> Dict[str, dict]:
    """path -> child, for every leaf child at any depth."""
    out = {}
    for prefix, sh in _walk(shell):
        for c in sh.children:
            if c.get("engine") != "structural":
                out[prefix + c["name"]] = c
    return out


def _mems(shell) -> Dict[str, Tuple[dict, dict]]:
    """path -> (leaf child, memory), for every memory member at any depth."""
    return {f"{p}.{m['name']}": (c, m) for p, c in _holders(shell).items()
            for m in c.get("mems", [])}


def _mem_storage(key: str, b: dict, m: dict) -> dict:
    """The checked binding of memory *m* (knob key *key*)."""
    bind = b.get("bind", "flops")
    if bind not in m["bindings"]:
        raise _err(key, f"a memory ({m['class']}) may be bound to {m['bindings']}, "
                        f"not {bind!r}")
    if bind == "wrapper" and not b.get("module"):
        raise _err(key, "bind: wrapper needs `module:`, the RAM module's name")
    if b.get("read_latency", 1) != 1:
        raise _err(key, f"read_latency {b['read_latency']}: {m['class']} is a RAM with a "
                        f"1-cycle read")
    out = {"bind": bind, "module": b["module"] if bind == "wrapper" else
           (b.get("macro") or RAM_1RW_MODEL) if bind == "sram" else RAM_1RW_MODEL}
    if b.get("files"):
        out["files"] = list(b["files"])
    return out


def _err(key: str, msg: str) -> XlsFlowError:
    return XlsFlowError(f"storage.{key}: {msg}")


def _check(key: str, b: dict, kind: str, depth: int, group: Optional[str]) -> None:
    bind = b.get("bind", "flops")
    allowed = librg.channel_bindings().get(kind, ())
    if bind not in allowed:
        raise _err(key, f"a {kind} channel may be bound to {list(allowed)}, not {bind!r}")
    if bind == "wrapper" and not b.get("module"):
        raise _err(key, "bind: wrapper needs `module:`, the wrapper's module name")
    if bind == "xls_fifo" and group is None:
        raise _err(key, "bind: xls_fifo is a FIFO inside an XLS package; this channel is "
                        "between blocks (put both ends in one island.groups group, or bind "
                        "it to flops, wrapper or sram)")
    if bind == "sram":
        if group is not None:
            raise _err(key, f"bind: sram is not available inside group {group!r} (XLS's FIFO "
                            f"module has no RAM ports); move the channel out of the group")
        if depth < SRAM_MIN_DEPTH:
            raise _err(key, f"bind: sram needs DEPTH {SRAM_MIN_DEPTH} or more (its output stage "
                            f"is two entries in flops); this channel has DEPTH {depth}")
        if b.get("read_latency", 1) != 1:
            raise _err(key, f"read_latency {b['read_latency']}: an SRAM FIFO takes a RAM "
                            f"with a 1-cycle read")


def _bits(bind: str, depth: int, bits: int) -> Tuple[Optional[int], int]:
    """(bits in flops, bits in RAM); flops unknown (None) for a wrapper."""
    if bind == "sram":
        return 2 * bits, (depth - 1) * bits
    if bind == "wrapper":
        return None, 0
    return depth * bits, 0


def plan(shell, knob: Optional[dict] = None) -> dict:
    """Resolve the ``storage:`` knob (*knob* is that section) against
    *shell*, write each channel's binding on it as ``storage``, and return
    the storage report. Raises :class:`XlsFlowError` for a binding that
    cannot be built, naming the knob key."""
    knob = dict(knob or {})
    default = dict(knob.pop("default", None) or {"bind": "flops"})
    chans = {p: (c, g) for p, c, g in _channels(shell)}
    holders = _holders(shell)
    mems = _mems(shell)
    for key, b in knob.items():
        if key in mems:
            continue
        if key in chans:
            c, _ = chans[key]
            if c.get("kind") == "level" or c["depth"] == 0:
                raise _err(key, "this channel holds no values (a level, or DEPTH 0, is a "
                                "wire); there is nothing to bind")
        elif key in holders:
            h = holders[key].get("holds")
            if h is None:
                raise _err(key, f"{holders[key]['class']} is not a storage class; its state "
                                f"is in flops, in its own block")
            if b.get("bind", "flops") not in h["bindings"]:
                raise _err(key, f"{holders[key]['class']} allows {h['bindings']} only: {h['why']}")
        else:
            tables = sorted(p for p, c in holders.items() if c.get("holds"))
            raise _err(key, f"no channel or storage instance {key!r} below the top; its "
                            f"channels are {sorted(chans)}"
                            + (f", its tables {tables}" if tables else "")
                            + (f", its memories {sorted(mems)}" if mems else ""))
    rows: List[dict] = []
    groups: Dict[str, Dict[str, list]] = {}
    for path, (c, g) in chans.items():
        kind, depth = c.get("kind", "ready_valid"), c["depth"]
        if kind == "level" or depth == 0:
            c.pop("storage", None)
            continue
        b = {**default, **knob.get(path, {})}
        _check(path if path in knob else "default", b, kind, depth, g)
        bind = b.get("bind", "flops")
        s = {"bind": bind}
        if bind == "wrapper":
            s["module"] = b["module"]
        if bind == "sram":
            s["macro"] = b.get("macro") or RAM_MODEL
        if b.get("files"):
            s["files"] = list(b["files"])
        c["storage"] = s
        if g is not None:
            groups.setdefault(g, {}).setdefault(_group_key(s), []).append(path)
        flop, ram = _bits(bind, depth, c.get("bits", 0))
        rows.append({"path": path, "kind": kind, "depth": depth, "bits": c.get("bits"),
                     "group": g, **s, "flop_bits": flop, "ram_bits": ram})
    for g, forms in groups.items():
        if len(forms) > 1:
            raise XlsFlowError(f"storage: the channels of group {g!r} are one XLS package, "
                               f"which takes one FIFO form; they differ: "
                               + "; ".join(f"{k} for {v}" for k, v in sorted(forms.items())))
    for path, (c, m) in mems.items():
        b = {**default, **knob.get(path, {})}
        st = _mem_storage(path if path in knob else "default", b, m)
        m["storage"] = st
        bits = m["words"] * m["bits"]
        flop, ram = (bits, 0) if st["bind"] == "flops" else \
            (None, 0) if st["bind"] == "wrapper" else (0, bits)
        rows.append({"path": path, "kind": "memory", "depth": m["words"], "bits": m["bits"],
                     "group": None, **st, "flop_bits": flop, "ram_bits": ram})
    for path, c in holders.items():
        if c.get("holds"):
            rows.append({"path": path, "class": c["class"], "bind": "flops",
                         "why": c["holds"]["why"]})
    return {"format": REPORT_FORMAT, "version": 1, "rows": rows}


def _group_key(s: dict) -> str:
    return s["bind"] if s["bind"] != "wrapper" else f"wrapper {s['module']}"


def group_flags(entry: dict) -> List[str]:
    """The codegen flags of a group: its FIFO form, from its channels'
    bindings (one form per package; :func:`plan` checks they agree)."""
    s = next((c["storage"] for c in entry.get("internal", []) if "storage" in c),
             {"bind": "flops"})
    if s["bind"] == "xls_fifo":
        return ["--multi_proc", "--materialize_internal_fifos"]
    if s["bind"] == "wrapper":
        return ["--multi_proc", f"--fifo_module={s['module']}"]
    return list(GROUP_FLOPS_FLAGS)


def files(shell) -> List[str]:
    """The extra RTL files the bindings name (a wrapper or a RAM shim)."""
    out: List[str] = []
    for _, c, _ in _channels(shell):
        out += [f for f in c.get("storage", {}).get("files", []) if f not in out]
    for _, m in _mems(shell).values():
        out += [f for f in m.get("storage", {}).get("files", []) if f not in out]
    return out


def format_report(rep: dict) -> str:
    """The report as a table."""
    lines = [f"{'instance':<24} {'bind':<9} {'depth x bits':>13} {'flop bits':>10} "
             f"{'RAM bits':>9}  module"]
    for r in rep["rows"]:
        if "class" in r:
            lines.append(f"{r['path']:<24} {'flops':<9} {'':>13} {'':>10} {'':>9}  "
                         f"{r['class']} (table: {r['why']})")
            continue
        mod = r.get("module") or r.get("macro") or ""
        flop = "?" if r["flop_bits"] is None else r["flop_bits"]
        shape = f"{r['depth']} x {r['bits']}"
        lines.append(f"{r['path']:<24} {r['bind']:<9} {shape:>13} "
                     f"{flop:>10} {r['ram_bits']:>9}  {mod}")
    return "\n".join(lines) + "\n"
