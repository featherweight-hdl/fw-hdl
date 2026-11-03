"""The generated latency table equals simulation, per knob set.

nb_top (tests/xls/compose/nb_pkg.sv): in -> a -> ch(1) -> p -> ch2(2) -> b -> out.
Each knob set changes stages and channel registers; the table's in -> out
latency must equal the first-value latency measured on the integrated RTL
(input always valid, output always ready). Everything runs through dv-flow.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from xls_harness import run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DFM = REPO / "packages" / "python" / "bin" / "dfm"

needs = pytest.mark.skipif(not DFM.exists() or codegen_main() is None or opt_main() is None,
                           reason="needs dfm, opt_main and codegen_main")

FLOW = """\
package:
  name: lr
  imports: [fw.hdl.spl, fw.hdl.knobs, fw.hdl.report, synth.xls, zuspec.xls]
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
  - {{name: rtl, uses: synth.xls.Codegen, needs: [part, knobs]}}
  - {{name: sig, uses: zuspec.xls.Signature, needs: [part, rtl]}}
  - {{name: top, uses: fw.hdl.spl.Integrate, needs: [part, sig]}}
  - {{name: lat, uses: fw.hdl.report.Latency, needs: [part, rtl]}}
  - {{name: all, needs: [top, lat]}}
"""

DESIGN = "design: {top: nb_top, xls: [nb_inc, nb_poll]}\n"
KNOB_SETS = {
    "k0": "xls: {default: {pipeline_stages: 1}}\n",
    "k1": "xls: {default: {pipeline_stages: 1}, blocks: {nb_inc: {pipeline_stages: 3}}}\n",
    "k2": "xls: {default: {pipeline_stages: 1, flop_inputs: true, flop_outputs: true}}\n",
    "k3": ("xls:\n  default: {pipeline_stages: 1}\n"
           "  chan_flop: {nb_poll.in: skid, nb_poll.out: flop}\n"),
    "k4": ("xls:\n  default: {pipeline_stages: 2}\n  blocks:\n"
           "    nb_inc: {flop_outputs: true, flop_outputs_kind: zerolatency}\n"
           "    nb_poll: {flop_inputs: true, flop_inputs_kind: skid}\n"),
}

# The knob sets really move the latency (and the register counts are as
# tests/xls/test_xls_facts.py says: flop/skid +1, zerolatency 0).
EXPECTED = {"k0": 2, "k1": 4, "k2": 8, "k3": 4, "k4": 6}

TB = """\
module xh_lat_tb;
  logic clk = 0, rst = 1;
  logic [7:0] in, out; logic in_vld = 0, in_rdy, out_vld, out_rdy = 1;
  int cyc = 0, tin = -1, tout = -1;
  nb_top dut(.*);
  initial begin
    repeat (3) begin #5 clk = 1; #5 clk = 0; end
    rst = 0; in = 8'd5; in_vld = 1;
    while (tout < 0 && cyc < 200) begin
      #1;
      if (tin < 0 && in_vld && in_rdy) tin = cyc;
      if (tout < 0 && out_vld && out_rdy) begin
        tout = cyc;
        if (out != 8'd7) $display("BAD %0d", out);
      end
      #4 clk = 1; #5 clk = 0;
      if (tin >= 0) in_vld = 0;
      cyc++;
    end
    $display("L %0d", tout - tin);
    $display("X done");
    $finish;
  end
endmodule
"""


def _outputs(rundir: Path, task: str):
    data = json.loads((rundir / task / f"{task}.exec_data.json").read_text())
    return data["output"]["output"]


@needs
@pytest.mark.verilator
@pytest.mark.parametrize("kset", sorted(KNOB_SETS))
def test_latency_predicted_equals_measured(tmp_path, kset):
    (tmp_path / "knobs.yaml").write_text(DESIGN + KNOB_SETS[kset])
    (tmp_path / "flow.yaml").write_text(FLOW.format(compose=HERE / "compose"))
    r = subprocess.run([str(DFM), "run", "all"], cwd=tmp_path, capture_output=True,
                       text=True, env=dict(os.environ))
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    rd = tmp_path / "rundir"
    rep = json.loads((rd / "lr.lat" / "latency.json").read_text())
    (path,) = [p for p in rep["paths"] if (p["src"], p["dst"]) == ("in", "out")]
    files = [Path(fs["basedir"]) / f for fs in _outputs(rd, "lr.top")
             if fs["filetype"] == "systemVerilogSource" for f in fs["files"]]
    tb = tmp_path / "xh_lat_tb.sv"
    tb.write_text(TB)
    out = run_verilator(files + [tb], "xh_lat_tb", tmp_path / "sim", with_lib=False)
    assert not [l for l in out if l.startswith("BAD")], out
    (measured,) = [int(l.split()[1]) for l in out if l.startswith("L ")]
    assert path["cycles"] == measured, (kset, path)
    assert measured == EXPECTED[kset]
