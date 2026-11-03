"""Per-block codegen from a knob file, through dv-flow only.

fw.hdl.spl.Partition -> xlsIR per block; fw.hdl.knobs.Resolve -> the
per-module codegen options; one synth.xls.Codegen task builds both blocks,
each with its own schedule, and records the toolchain it ran.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DFM = REPO / "packages" / "python" / "bin" / "dfm"

needs = pytest.mark.skipif(not DFM.exists() or codegen_main() is None or opt_main() is None,
                           reason="needs dfm, opt_main and codegen_main")

FLOW = """\
package:
  name: bc
  imports: [fw.hdl.spl, fw.hdl.knobs, synth.xls]
  tasks:
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {compose}, include: [nb_pkg.sv]}}
  - name: knob-file
    uses: std.FileSet
    with: {{type: fwKnobFile, include: [{knobs}]}}
  - name: knobs
    uses: fw.hdl.knobs.Resolve
    needs: [knob-file]
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src]
    with: {{top: nb_top, xls: [nb_inc, nb_poll]}}
  - name: rtl
    uses: synth.xls.Codegen
    needs: [part, knobs]
"""

KNOBS = """\
design: {top: nb_top, xls: [nb_inc, nb_poll]}
xls:
  default: {pipeline_stages: 1}
  blocks:
    nb_inc: {pipeline_stages: %d, flop_outputs: true}
"""


@needs
@pytest.mark.parametrize("stages", [2, 3])
def test_block_codegen_from_knobs(tmp_path, stages):
    (tmp_path / "k.yaml").write_text(KNOBS % stages)
    (tmp_path / "flow.yaml").write_text(FLOW.format(compose=HERE / "compose", knobs="k.yaml"))
    r = subprocess.run([str(DFM), "run", "rtl"], cwd=tmp_path, capture_output=True,
                       text=True, env=dict(os.environ))
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    rd = tmp_path / "rundir" / "bc.rtl"
    n = {p.name: p.read_text().count("stages {") for p in rd.glob("*.schedule.textproto")}
    assert n == {"nb_inc.schedule.textproto": stages, "nb_poll.schedule.textproto": 1}
    tc = json.loads((rd / "toolchain.json").read_text())
    cg = next(t for t in tc["tools"] if t["tool"] == "codegen_main")
    assert cg["release"] and len(cg["sha256"]) == 64


DCAL_FLOW = """\
package:
  name: dc
  imports: [fw.hdl.spl, fw.hdl.knobs, synth.xls]
  tasks:
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {compose}, include: [crit_pkg.sv]}}
  - name: knob-file
    uses: std.FileSet
    with: {{type: fwKnobFile, include: [k.yaml]}}
  - {{name: knobs, uses: fw.hdl.knobs.Resolve, needs: [knob-file]}}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src]
    with: {{top: crit_top, xls: [crit_blk]}}
  - {{name: rtl, uses: synth.xls.Codegen, needs: [part, knobs]}}
"""


@needs
def test_delay_scale_reschedules(tmp_path):
    """delay.scale multiplies the period handed to the scheduler, so
    a pessimistic delay model (scale > 1) takes fewer stages at one target."""
    stages = {}
    for scale in (1.0, 3.0):
        d = tmp_path / f"s{scale}"
        d.mkdir()
        (d / "k.yaml").write_text(
            "design: {top: crit_top, xls: [crit_blk]}\n"
            "xls: {default: {clock_period_ps: 800, delay_model: asap7}}\n"
            f"delay: {{scale: {scale}}}\n")
        (d / "flow.yaml").write_text(DCAL_FLOW.format(compose=HERE / "compose"))
        r = subprocess.run([str(DFM), "run", "rtl"], cwd=d, capture_output=True, text=True,
                           env=dict(os.environ))
        assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
        sched = (d / "rundir" / "dc.rtl" / "crit_blk.schedule.textproto").read_text()
        stages[scale] = sched.count("stages {")
    assert stages[1.0] > stages[3.0] >= 1, stages
