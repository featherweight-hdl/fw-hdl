"""fw-hdl's transactor kits: where they live and how their SV is read.

The kit descriptors (``zuspec.kit`` v1) sit next to their SV under ``src/std``
(``fw_put_kit.yaml``, ``rv/fw_rv_kit.yaml``); :func:`registry` loads them, plus
any project kit directories. :func:`sv_port_reader` reads a module's real port
list with pyslang, for the stale-map check (``zuspec.synth.kits.check_ports``),
so zuspec-synth needs no SV parser of its own.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

from zuspec.synth.kits import KitRegistry, PortReader, check_ports

from .fe.parser import FW_LIB_INCDIRS

_STD = Path(FW_LIB_INCDIRS[1])

#: fw-hdl's own kit directory.
STD_KIT_PATHS: List[str] = [str(_STD)]

_DIR = {"input": "in", "output": "out", "inout": "inout"}


def kit_paths(extra: Iterable[str] = ()) -> List[str]:
    return STD_KIT_PATHS + [str(p) for p in extra]


@functools.lru_cache(maxsize=None)
def _std_registry() -> KitRegistry:
    return KitRegistry(STD_KIT_PATHS)


def registry(extra: Sequence[str] = ()) -> KitRegistry:
    """The std kits, plus kits under *extra* (project directories)."""
    if not extra:
        return _std_registry()
    return KitRegistry(kit_paths(extra))


def sv_ports(files: Iterable[str]) -> Dict[str, Dict[str, str]]:
    """``{module or interface: {port: "in"|"out"|"inout"}}`` for every ANSI
    port list in *files* (syntax only: no elaboration, so `type` parameters
    need no values)."""
    from pyslang import syntax
    out: Dict[str, Dict[str, str]] = {}
    for f in files:
        tree = syntax.SyntaxTree.fromFile(str(f))
        for m in tree.root.members:
            hdr = getattr(m, "header", None)
            ports = getattr(getattr(hdr, "ports", None), "ports", None)
            if hdr is None or ports is None:
                continue
            d: Dict[str, str] = {}
            last = "inout"
            for p in ports:
                ph = getattr(p, "header", None)
                if ph is None:
                    continue                        # a separator
                tok = getattr(ph, "direction", None)
                if tok is not None and tok.valueText:
                    last = _DIR.get(tok.valueText, tok.valueText)
                d[p.declarator.name.valueText] = last
            out[hdr.name.valueText] = d
    return out


def sv_port_reader(files: Iterable[str]) -> PortReader:
    ports = sv_ports(files)
    return lambda module: ports[module]


def std_sv_files() -> List[str]:
    """Every SV unit under ``src/std`` that a kit names a module in."""
    return sorted(str(p) for p in _STD.rglob("*.sv"))


def check_kits(reg: KitRegistry, files: Iterable[str]) -> List[str]:
    """R6 over every transactor of *reg*, against the SV in *files*."""
    reader = sv_port_reader(files)
    return [e for t in reg.transactors() for e in check_ports(t, reader)]
