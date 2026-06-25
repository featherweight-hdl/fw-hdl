"""``fw-hdl`` command-line interface.

Sub-commands mirror the IR pipeline (DESIGN §6):

    fw-hdl sv2ir   <files...>   FW-SV   -> SPL IR
    fw-hdl spl2rtl <ir>         SPL IR  -> RTL IR
    fw-hdl rtl2v   <ir>         RTL IR  -> Verilog
    fw-hdl synth   <files...>   FW-SV   -> Verilog (+report), full flow
    fw-hdl synth-mmio <files>    FW-SV  -> {regblock, fsm(s), top}.sv (MMIO design)

Follows SystemVerilog tool conventions for include/define: ``+incdir+<path>`` and
``+define+<name>[=<val>]`` (with ``-I``/``-D`` long aliases).

Only ``sv2ir`` (AST dump) is wired up at P0; later stages are placeholders.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Tuple

from .config import FlowConfig
from .errors import ErrorReporter


# ---------------------------------------------------------------------------
# plusarg handling (+incdir+, +define+) — argparse doesn't grok '+'-prefixed args
# ---------------------------------------------------------------------------
def _split_plusargs(argv: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """Return (incdirs, defines, remaining_argv) pulling ``+incdir+``/``+define+``."""
    incdirs: List[str] = []
    defines: List[str] = []
    rest: List[str] = []
    for tok in argv:
        if tok.startswith("+incdir+"):
            incdirs.extend(p for p in tok[len("+incdir+"):].split("+") if p)
        elif tok.startswith("+define+"):
            defines.extend(d for d in tok[len("+define+"):].split("+") if d)
        else:
            rest.append(tok)
    return incdirs, defines, rest


def _parse_define(item: str) -> Tuple[str, str]:
    name, _, value = item.partition("=")
    return name, value


def _config_from_args(args: argparse.Namespace,
                      plus_incdirs: List[str],
                      plus_defines: List[str]) -> FlowConfig:
    cfg = FlowConfig()
    cfg.incdirs = list(plus_incdirs) + list(getattr(args, "incdir", None) or [])
    for d in list(plus_defines) + list(getattr(args, "define", None) or []):
        name, value = _parse_define(d)
        cfg.defines[name] = value
    cfg.top = getattr(args, "top", None)
    cfg.top_module = getattr(args, "top_module", None)
    cfg.reset_style = getattr(args, "reset_style", "sync_low")
    cfg.output = getattr(args, "output", None)
    cfg.dump_ir = getattr(args, "dump_ir", False)
    return cfg


# ---------------------------------------------------------------------------
# argument parser
# ---------------------------------------------------------------------------
def _add_common(p: argparse.ArgumentParser, *, with_top: bool = True) -> None:
    p.add_argument("files", nargs="*", help="input file(s)")
    p.add_argument("-I", "--incdir", action="append", default=[],
                   help="include search path (also +incdir+<path>)")
    p.add_argument("-D", "--define", action="append", default=[],
                   help="preprocessor define name[=val] (also +define+<name>[=val])")
    p.add_argument("-o", "--output", help="output file or directory")
    if with_top:
        p.add_argument("--top", help="root component class (e.g. blinky)")
        p.add_argument("--top-module", dest="top_module",
                       help="*_top module carrying the fw_root binding")
        p.add_argument("--reset-style", dest="reset_style", default="async_high",
                       choices=["async_high", "sync_high", "sync_low", "async_low"])
    p.add_argument("--dump-ir", dest="dump_ir", action="store_true",
                   help="dump intermediate IR")
    p.add_argument("--dump-ast", dest="dump_ast", action="store_true",
                   help="(debug) dump the raw pyslang class listing")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fw-hdl", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    _add_common(sub.add_parser("sv2ir", help="FW-SystemVerilog -> SPL IR"))
    _add_common(sub.add_parser("spl2rtl", help="SPL IR -> RTL IR"))
    _add_common(sub.add_parser("rtl2v", help="RTL IR -> Verilog"))
    _add_common(sub.add_parser("synth", help="full flow: FW-SV -> Verilog + report"))
    sm = sub.add_parser(
        "synth-mmio",
        help="MMIO register-model design: FW-SV -> {regblock, fsm(s), top}.sv")
    _add_common(sm)
    sm.add_argument("--component", action="append", dest="components",
                    help="MMIO FSM class to include (repeatable; default: all)")
    return parser


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def _cmd_sv2ir(cfg: FlowConfig, files: List[str], *, dump_ast: bool = False) -> int:
    """Map FW-SystemVerilog to SPL IR (``--dump-ir`` prints a textual IR view).

    ``--dump-ast`` (debug) prints the raw pyslang class listing instead.
    """
    if not files:
        print("fw-hdl sv2ir: no input files", file=sys.stderr)
        return 2

    reporter = ErrorReporter()

    if dump_ast:
        from .fe.parser import Parser
        from .fe import astdump
        parser = Parser(cfg, reporter)
        if not parser.parse(files):
            print(reporter.report(), file=sys.stderr)
            return 1
        astdump.dump(parser.get_root(), top=cfg.top, out=sys.stdout)
        return 0

    from .fe.context import build_spl_context
    from .ir_text import dump_context

    ctxt = build_spl_context(files, cfg, reporter)
    if ctxt is None:
        print(reporter.report(), file=sys.stderr)
        return 1

    dump_context(ctxt, out=sys.stdout)
    return 0


def _cmd_spl2rtl(cfg: FlowConfig, files: List[str]) -> int:
    """Lower FW-SV -> SPL IR -> RTL IR and dump the RTL IR.

    (IR-artifact round-trip via the JSON serializer is a later nicety; for now
    this verb runs from source and shows the RTL-level IR.)
    """
    from . import flow
    from .ir_text import dump_context
    reporter = ErrorReporter()
    spl = flow.run_sv2ir(files, cfg, reporter)
    rtl = flow.run_spl2rtl(spl, cfg, reporter) if spl is not None else None
    if rtl is None:
        print(reporter.report(), file=sys.stderr)
        return 1
    dump_context(rtl, out=sys.stdout)
    return 0


def _cmd_rtl2v(cfg: FlowConfig, files: List[str]) -> int:
    """Lower and emit Verilog (FW-SV -> ... -> RTL)."""
    return _run_synth(cfg, files, with_report=False)


def _cmd_synth(cfg: FlowConfig, files: List[str]) -> int:
    return _run_synth(cfg, files, with_report=True)


def _cmd_synth_mmio(cfg: FlowConfig, files: List[str], *,
                    components: Optional[List[str]] = None) -> int:
    """Synthesize an MMIO design into {regblock, fsm(s), top}.sv.

    With ``-o <dir>`` (a path ending in ``/`` or an existing directory) the
    modules are written there; otherwise they are concatenated to stdout.
    """
    import os
    from .mmio_synth import synth_mmio_design

    if not files:
        print("fw-hdl synth-mmio: no input files", file=sys.stderr)
        return 2
    reporter = ErrorReporter()
    design = synth_mmio_design(files, cfg, reporter, components=components,
                               top_name=cfg.top_module)
    if design is None:
        print(reporter.report(), file=sys.stderr)
        return 1

    out = cfg.output
    if out and (out.endswith("/") or os.path.isdir(out)):
        os.makedirs(out, exist_ok=True)
        for fn, txt in design.files().items():
            with open(os.path.join(out, fn), "w") as fh:
                fh.write(txt if txt.endswith("\n") else txt + "\n")
        print(f"wrote {', '.join(design.files())} to {out}", file=sys.stderr)
    else:
        for fn, txt in design.files().items():
            print(f"// ==== {fn} ====")
            print(txt)
    return 0


def _run_synth(cfg: FlowConfig, files: List[str], *, with_report: bool) -> int:
    from . import flow
    if not files:
        print("fw-hdl: no input files", file=sys.stderr)
        return 2
    reporter = ErrorReporter()
    result = flow.synth(files, cfg, reporter)
    if result is None:
        print(reporter.report(), file=sys.stderr)
        return 1
    if cfg.output and not cfg.output.endswith("/"):
        with open(cfg.output, "w") as fh:
            fh.write(result.sv if result.sv.endswith("\n") else result.sv + "\n")
    else:
        print(result.sv)
    if with_report:
        print(result.report, file=sys.stderr)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    plus_incdirs, plus_defines, rest = _split_plusargs(raw)
    args = _build_parser().parse_args(rest)
    cfg = _config_from_args(args, plus_incdirs, plus_defines)

    if args.command == "sv2ir":
        return _cmd_sv2ir(cfg, args.files, dump_ast=getattr(args, "dump_ast", False))
    if args.command == "spl2rtl":
        return _cmd_spl2rtl(cfg, args.files)
    if args.command == "rtl2v":
        return _cmd_rtl2v(cfg, args.files)
    if args.command == "synth":
        return _cmd_synth(cfg, args.files)
    if args.command == "synth-mmio":
        return _cmd_synth_mmio(cfg, args.files,
                               components=getattr(args, "components", None))
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
