"""The XLS engine adapter builds what the flow builds (phase0-plan.md exit 2).

For each example block, ``XlsEngine.build`` must produce the same XLS IR as
``fw.hdl.xls.IR`` and byte-identical Verilog to ``synth.xls.Codegen``, as run
by the example's own flow (``dfm run <example>.rtl``). It must also return an
overlay whose interface is XLS's signature.
"""
import os
import subprocess

import pytest

import zuspec.ir.core as ir
from zuspec.ir.core.anchor import assign_anchors
from zuspec.ir.core.engine import Constraints, get_engine
from zuspec.be.xls.engine import _lower
from zuspec.be.xls.printer import format_package
from zuspec.be.xls.signature import signature_from_codegen
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

from fw.hdl.config import FlowConfig
from fw.hdl.spl_flow import module_name
from fw.hdl.xls_flow import sv_to_component, sv_to_functions
from xls_harness import REPO

EX = REPO / "examples" / "xls"
RUN = EX / "rundir"
SRC = REPO / "src"
STD = [str(EX / "common" / "xls_std_pkg.sv")]
FW_LIB = [str(SRC / "fw_hdl_pkg.sv"), str(SRC / "fw_clock_xtor_if.sv"),
          str(SRC / "std" / "fw_std_pkg.sv")]
VALID = {"input_valid_signal": "input_valid", "output_valid_signal": "output_valid"}

CASES = [
    # example, files, top, is_function, Codegen params beyond the defaults
    ("gcd", STD + [str(EX / "gcd" / "gcd_pkg.sv")], "gcd_pkg::gcd_binary8", True, VALID),
    ("aes", [str(EX / "aes" / "aes_pkg.sv")], "aes_pkg::encrypt", True, VALID),
    ("lfsr", [str(EX / "lfsr" / "lfsr_pkg.sv")], "lfsr_pkg::lfsr8", True, VALID),
    ("rle", FW_LIB + [str(EX / "rle" / "rle_pkg.sv")], "RunLengthEncoder32", False, {}),
]

needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="XLS tools not found")


@pytest.fixture(scope="module")
def flow_rtl():
    """Run each example's own `rtl` task (up to date when already built)."""
    done = {}

    def get(example):
        if example not in done:
            log = RUN / f"test_engine_path.{example}.log"
            RUN.mkdir(exist_ok=True)
            with open(log, "w") as f:
                r = subprocess.run(["dfm", "run", f"xls_examples.{example}.rtl"], cwd=EX, stdout=f,
                                   stderr=subprocess.STDOUT)
            assert r.returncode == 0, f"dfm run xls_examples.{example}.rtl failed (see {log})"
            done[example] = RUN / f"xls_examples.{example}.rtl"
        return done[example]
    return get


def roots_of(files, top, is_fn):
    module = module_name(top)
    config = FlowConfig(incdirs=[str(SRC), str(SRC / "std")])
    if is_fn:
        return sv_to_functions(files, [top], config, rename={top: module}), module
    return [sv_to_component(files, top, config)], module


@needs_xls
@pytest.mark.parametrize("example,files,top,is_fn,params", CASES,
                         ids=[c[0] for c in CASES])
def test_engine_matches_flow(tmp_path, flow_rtl, example, files, top, is_fn, params):
    rtl_dir = flow_rtl(example)
    roots, module = roots_of(files, top, is_fn)
    ir_top = module if is_fn else roots[0].name
    # The same XLS IR as fw.hdl.xls.IR wrote.
    flow_ir = (RUN / f"xls_examples.{example}.ir" / f"{module}.ir").read_text()
    assert format_package(_lower(roots, ir_top)) == flow_ir
    # Byte-identical Verilog to synth.xls.Codegen's.
    anchors = assign_anchors(roots)
    res = get_engine("xls").build(roots, ir_top, anchors,
                                  Constraints(pipeline_stages=2, extra=dict(params)),
                                  str(tmp_path))
    assert res.top_module == module
    assert open(res.rtl[0]).read() == (rtl_dir / f"{module}.sv").read_text()
    # The overlay carries XLS's own signature as the block's interface, with
    # each channel's stage filled in from the schedule (XLS v0.59's signature
    # has no stage field; docs/overlay-xls.md).
    sig = ir.signature_to_json(signature_from_codegen(
        (rtl_dir / f"{module}.sig.textproto").read_text()))
    got = res.overlay.column("iface.block")["value"][0]
    for c in got.get("channels", []):
        assert c.pop("stage", None) is not None, c["name"]
    for c in sig.get("channels", []):
        c.pop("stage", None)
    assert got == sig
    assert res.overlay.header.engine_version is not None
    assert res.overlay.column("sched.stage")["anchor"]
