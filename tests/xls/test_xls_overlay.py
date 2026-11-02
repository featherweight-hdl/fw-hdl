"""XLS results as a Zuspec overlay, end to end: SV -> IR (anchored) -> XLS ->
facts on the SV's anchors (phase0-plan.md C6)."""
import json
import os
import subprocess
from pathlib import Path

import pytest

import zuspec.ir.core as ir
from zuspec.ir.core.anchor import assign_anchors
from zuspec.ir.core.results import ResultStore, VALID
from zuspec.be.xls import xir
from zuspec.be.xls.lower_fn import lower_functions
from zuspec.be.xls.lower_proc import lower_component
from zuspec.be.xls.overlay import xls_overlay
from zuspec.be.xls.printer import format_package
from zuspec.be.xls.signature import signature_from_codegen
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

from fw.hdl.xls_flow import sv_to_component, sv_to_functions
from xls_harness import REPO

needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="XLS tools not found")

GCD = [str(REPO / "examples/xls/common/xls_std_pkg.sv"),
       str(REPO / "examples/xls/gcd/gcd_pkg.sv")]
RLE = [str(REPO / "tests/xls/corpus/rle_pkg.sv"), str(REPO / "tests/xls/corpus/rle8_pkg.sv")]
GOLDEN = Path(__file__).parent / "golden" / "mapping_coverage.json"


def run_xls(pkg: xir.Package, workdir: Path, stages: int, module: str, extra=()):
    """opt_main then codegen_main with every output the overlay reads."""
    workdir.mkdir(parents=True, exist_ok=True)
    src = workdir / "in.ir"
    src.write_text(format_package(pkg))
    opt = workdir / "opt.ir"
    subprocess.run([opt_main(), str(src), f"--output_path={opt}"], check=True,
                   capture_output=True)
    out = {k: workdir / f"{module}.{k}" for k in
           ("sv", "sig", "sched", "sched_ir", "block_ir", "line_map")}
    subprocess.run([codegen_main(), str(opt), "--generator=pipeline", "--delay_model=unit",
                    f"--pipeline_stages={stages}", f"--module_name={module}", "--reset=rst",
                    f"--output_verilog_path={out['sv']}",
                    f"--output_signature_path={out['sig']}",
                    f"--output_schedule_path={out['sched']}",
                    f"--output_schedule_ir_path={out['sched_ir']}",
                    f"--output_block_ir_path={out['block_ir']}",
                    f"--output_verilog_line_map_path={out['line_map']}", *extra],
                   check=True, capture_output=True)
    return {k: p.read_text() for k, p in out.items()}


def overlay_of(table, art, **kw):
    return xls_overlay(table, ir_text=art["sched_ir"], schedule_text=art["sched"],
                       signature_text=art["sig"], block_ir_text=art["block_ir"], **kw)


def record_coverage(name, o):
    """Coverage is gated against regression, not against a bar: lossy engines
    are acceptable (phase0-plan.md C6, golden/mapping_coverage.json)."""
    golden = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
    cov = o.header.coverage
    if os.environ.get("UPDATE_GOLDEN") or name not in golden:
        golden[name] = {k: cov[k] for k in ("pct_ops_attributed", "pct_crit_delay_attributed")}
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
        return
    for k, was in golden[name].items():
        if was is not None:
            assert cov[k] is not None and cov[k] >= was - 2.0, \
                f"{name}: {k} fell from {was} to {cov[k]} (UPDATE_GOLDEN=1 if intended)"


@needs_xls
def test_gcd_function_overlay(tmp_path):
    fns = sv_to_functions(GCD, ["gcd_pkg::gcd_binary8"],
                          rename={"gcd_pkg::gcd_binary8": "gcd_pkg__gcd_binary8"})
    table = assign_anchors(fns)
    pkg = xir.Package(name="gcd_pkg__gcd_binary8")
    lower_functions(pkg, fns)
    pkg.top = "gcd_pkg__gcd_binary8"
    art = run_xls(pkg, tmp_path, 2, "gcd_pkg__gcd_binary8",
                  ["--input_valid_signal=input_valid", "--output_valid_signal=output_valid"])
    o = overlay_of(table, art)
    blk = "gcd_pkg__gcd_binary8"
    # The interface is today's signature, as a fact on the block.
    assert o.column("iface.block")["anchor"] == [blk]
    assert o.column("iface.block")["value"][0] == \
        ir.signature_to_json(signature_from_codegen(art["sig"]))
    assert o.column("sched.stage_count")["value"] == [2]
    # Every scheduled operation has a stage, on an anchor of the SV source.
    stages = o.column("sched.stage")
    assert stages["anchor"] and all(a in table for a in stages["anchor"])
    assert set(stages["value"]) <= {0, 1}
    # Registers are derived anchors of the SV expressions they carry.
    regs = o.column("rtl.register")
    assert regs["anchor"] and all("@reg:" in a for a in regs["anchor"])
    # Through a store, looked up from the IR node.
    store = ResultStore(table)
    store.add(o)
    node = table.node_of(stages["anchor"][0])
    assert any(v.status == VALID for v in store.facts(node, kind="sched.stage"))
    record_coverage("gcd_binary8", o)


@needs_xls
def test_rle_proc_overlay(tmp_path):
    comp = sv_to_component(RLE, "rle_enc8_t")
    table = assign_anchors(comp)
    pkg = lower_component(comp)
    art = run_xls(pkg, tmp_path, 2, "rle_enc8")
    o = overlay_of(table, art, top=pkg.top, block_anchor=comp.anchor)
    sig = o.column("iface.block")["value"][0]
    assert {c["name"] for c in sig["channels"]} >= {"in", "out"}
    # Channel stages come from where the send/receive is scheduled.
    assert all(c["stage"] is not None for c in sig["channels"])
    assert o.column("sched.ii")["value"][0]["reliable"] is False
    assert o.column("sched.stage")["anchor"]
    record_coverage("rle_enc8", o)
