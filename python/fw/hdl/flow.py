"""The fw-hdl flow orchestrator.

Chains the three IR levels — ``sv2ir`` (FW-SV → SPL IR), ``spl2rtl`` (SPL IR →
RTL IR), ``rtl2v`` (RTL IR → Verilog) — and produces a small synthesis report.
"""
from __future__ import annotations

import dataclasses as dc
from typing import List, Optional, Tuple

import zuspec.ir.core as ir

from .config import FlowConfig
from .emit.be_sv import emit_sv
from .errors import ErrorReporter
from .fe.context import build_spl_context
from .lower.spl2rtl import lower_context


def run_sv2ir(files: List[str], config: FlowConfig,
              reporter: ErrorReporter) -> Optional[ir.Context]:
    return build_spl_context(files, config, reporter)


def run_spl2rtl(spl: ir.Context, config: FlowConfig,
                reporter: ErrorReporter) -> Optional[ir.Context]:
    return lower_context(spl, config, reporter)


def run_rtl2v(rtl: ir.Context, config: FlowConfig) -> str:
    return emit_sv(rtl, top=config.top, out_dir=None)


@dc.dataclass
class SynthResult:
    sv: str
    report: str
    rtl: ir.Context


def synth(files: List[str], config: FlowConfig,
          reporter: ErrorReporter) -> Optional[SynthResult]:
    """Full flow: FW-SV -> Verilog (+report)."""
    spl = run_sv2ir(files, config, reporter)
    if spl is None:
        return None
    rtl = run_spl2rtl(spl, config, reporter)
    if rtl is None:
        return None
    sv = emit_sv(rtl, top=config.top, out_dir=config.output if _is_dir(config.output) else None)
    return SynthResult(sv=sv, report=_report(rtl), rtl=rtl)


def _is_dir(path: Optional[str]) -> bool:
    import os
    return bool(path) and (path.endswith("/") or os.path.isdir(path))


def _report(rtl: ir.Context) -> str:
    lines = ["# fw-hdl synthesis report"]
    for name, dtype in rtl.type_m.items():
        if not isinstance(dtype, ir.DataTypeComponent):
            continue
        inputs = [f for f in dtype.fields if isinstance(f, ir.FieldInOut) and not f.is_out]
        outputs = [f for f in dtype.fields if isinstance(f, ir.FieldInOut) and f.is_out]
        regs = [f for f in dtype.fields
                if getattr(f, "is_reg", False)
                or (isinstance(f, ir.FieldInOut) and f.is_out)]
        lines.append(f"module {name}:")
        lines.append(f"  inputs : {', '.join(f.name for f in inputs) or '-'}")
        lines.append(f"  outputs: {', '.join(f.name for f in outputs) or '-'}")
        lines.append(f"  registers ({len(regs)}): "
                     f"{', '.join(f.name for f in regs) or '-'}")
        lines.append(f"  clocked processes: {len(dtype.sync_processes)}")
    return "\n".join(lines)
