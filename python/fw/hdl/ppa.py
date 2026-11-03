"""RQ-R2: critical-path attribution per block (``xls_ppa.csv``).

For each block: its stage count, initiation interval, the critical path's
delay, and the *dominant source line* -- the line whose nodes contribute the
most delay to that path. It answers "which line do I change to close timing"
at the schedule level, before synthesis.

The path is the one XLS's schedule shows (``dv_flow.libsynth.xls.diag``):
the node with the largest path delay, traced back through the operand it
extends.
"""
from __future__ import annotations

import csv
import dataclasses as dc
import io
import os
from typing import Dict, List, Optional, Sequence, Tuple

COLUMNS = ("block", "stages", "ii", "crit_ps", "crit_src", "crit_src_ps", "path")


@dc.dataclass
class BlockPpa:
    block: str
    stages: int
    ii: Optional[int]
    crit_ps: int
    crit_src: str            # "file:line" of the dominant line, or "" if none is known
    crit_src_ps: int         # that line's share of crit_ps
    path: str                # the path as "file:line -> file:line ..."

    def row(self) -> List:
        return [getattr(self, c) for c in COLUMNS]


def block_ppa(block: str, opt_ir: str, schedule: str, srcdir: Optional[str] = None,
              ii: Optional[int] = None) -> BlockPpa:
    from dv_flow.libsynth.xls import diag
    idx = diag.IrIndex(opt_ir, srcdir)
    sched = diag.parse_schedule(schedule)
    stages = 1 + max((t.stage for t in sched.values()), default=0)
    path = diag.critical_path(sched, idx)
    crit = path[-1].path_delay if path else 0
    share: Dict[Tuple[str, int], int] = {}
    order: List[str] = []
    for t in path:
        locs = idx.locate(t.name)
        if not locs:
            continue
        key = (locs[0][0], locs[0][1])
        share[key] = share.get(key, 0) + t.node_delay
        s = f"{os.path.basename(key[0])}:{key[1]}"
        if not order or order[-1] != s:
            order.append(s)
    if share:
        (f, line), ps = max(share.items(), key=lambda kv: kv[1])
        src = f"{f}:{line}"
    else:
        src, ps = "", 0
    return BlockPpa(block, stages, ii, crit, src, ps, " -> ".join(order))


def load(files: Sequence[Tuple[str, str, str, Optional[int]]]) -> List[BlockPpa]:
    """``[(block, opt_ir_path, schedule_path, ii|None)]``."""
    out = []
    for block, opt, sched, ii in files:
        with open(opt) as f, open(sched) as g:
            out.append(block_ppa(block, f.read(), g.read(), os.path.dirname(opt), ii))
    return out


def to_csv(rows: Sequence[BlockPpa]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow(r.row())
    return buf.getvalue()
