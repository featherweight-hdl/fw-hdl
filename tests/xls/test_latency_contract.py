"""Latency contracts in the knob file.

nb_top: in -> a(nb_inc) -> ch(1) -> p(nb_poll) -> ch2(2) -> b(nb_inc) -> out.
The channels alone cost 2 cycles; each block costs its registers plus
0..stages-1.
"""
import json
import os
import subprocess
from pathlib import Path
from fw_tools import tool

import pytest

from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DFM = tool("dfm")

needs = pytest.mark.skipif(not DFM.exists() or codegen_main() is None or opt_main() is None,
                           reason="needs dfm, opt_main and codegen_main")

FLOW = """\
package:
  name: lc
  imports: [fw.hdl.spl, fw.hdl.knobs, fw.hdl.check, fw.hdl.report, synth.xls]
  tasks:
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {compose}, include: [nb_pkg.sv]}}
  - name: knob-file
    uses: std.FileSet
    with: {{type: fwKnobFile, include: [knobs.yaml]}}
  - {{name: knobs, uses: fw.hdl.knobs.Resolve, needs: [knob-file]}}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src, knobs]
    with: {{top: nb_top, xls: [nb_inc, nb_poll]}}
  - {{name: contracts, uses: fw.hdl.check.Contracts, needs: [part, knobs]}}
  - {{name: rtl, uses: synth.xls.Codegen, needs: [part, knobs, contracts]}}
  - {{name: lat, uses: fw.hdl.report.Latency, needs: [part, rtl, knobs]}}
"""

DESIGN = "design: {top: nb_top, xls: [nb_inc, nb_poll]}\n"


def run(tmp_path, knobs):
    (tmp_path / "knobs.yaml").write_text(DESIGN + knobs)
    (tmp_path / "flow.yaml").write_text(FLOW.format(compose=HERE / "compose"))
    r = subprocess.run([str(DFM), "run", "lat"], cwd=tmp_path, capture_output=True,
                       text=True, env=dict(os.environ))
    return r.returncode, " ".join((r.stdout + r.stderr).split()), tmp_path / "rundir"


@needs
def test_contract_met(tmp_path):
    rc, out, rd = run(tmp_path, "xls: {default: {pipeline_stages: 1}}\n"
                                "contracts: {latency: {'in -> out': {max: 2}}}\n")
    assert rc == 0, out[-2000:]


@needs
@pytest.mark.parametrize("knobs,why", [
    ("xls: {default: {pipeline_stages: 1}}\n"
     "contracts: {latency: {'in -> out': {max: 1}}}\n", "path in -> out 2..2"),
    ("xls: {default: {pipeline_stages: 2, flop_inputs: true, flop_outputs: true}}\n"
     "contracts: {latency: {'in -> out': {max: 4}}}\n", "path in -> out 8..11"),
    ("xls: {default: {pipeline_stages: 1}}\n"
     "contracts: {latency: {'nb_inc.in -> nb_inc.out': {fixed: 2}}}\n",
     "block nb_inc in -> out 0..0"),
])
def test_rejected_before_codegen(tmp_path, knobs, why):
    rc, out, rd = run(tmp_path, knobs)
    assert rc != 0 and "cannot be met" in out and why in out, out[-2000:]
    assert not (rd / "lc.rtl").exists() or not list((rd / "lc.rtl").glob("*.sv")), \
        "codegen ran although the contract check failed"


@needs
def test_block_contract_drives_the_scheduler(tmp_path):
    """nb_inc.in -> nb_inc.out fixed 2 with 3 stages: XLS places the send two
    stages after the receive (its free schedule took 1), and the report sees it."""
    rc, out, rd = run(tmp_path, "xls: {default: {pipeline_stages: 1}, "
                                "blocks: {nb_inc: {pipeline_stages: 3}}}\n"
                                "contracts: {latency: {'nb_inc.in -> nb_inc.out': {fixed: 2}}}\n")
    assert rc == 0, out[-2000:]
    rep = json.loads((rd / "lc.lat" / "latency.json").read_text())
    (p,) = rep["paths"]
    assert [h["cycles"] for h in p["hops"] if h["what"] == "block" and h["name"] in "ab"] \
        == [2, 2]
    assert p["cycles"] == 6


@needs
def test_violation_found_after_codegen(tmp_path):
    """The knobs allow 2..6 cycles, so the pre-check passes a min of 6; the
    schedule XLS picks gives 4, and the report fails it."""
    rc, out, rd = run(tmp_path, "xls: {default: {pipeline_stages: 1}, "
                                "blocks: {nb_inc: {pipeline_stages: 3}}}\n"
                                "contracts: {latency: {'in -> out': {min: 6}}}\n")
    assert rc != 0 and "violated: in -> out takes 4 cycles" in out, out[-2000:]
