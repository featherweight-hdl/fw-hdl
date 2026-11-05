"""Declared characterization facts on wrapped IP (src/fw_facts.svh,
fw.hdl.facts): a leaf's facts() and sidecar files reach the partition, the
Partition task writes them as an overlay of provenance "declared", and the
latency report goes through wrapped and structural children with them.

fix_top's path has only fixed hops (a structural child holding a wrapped
FIFO and an XLS block, then another wrapped FIFO): its predicted latency is
the measured one. rng_top declares a range for its last FIFO: the measured
latency lies inside the predicted range, and the path is unverified.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from fw.hdl import latency
from fw.hdl.errors import FwHdlError
from fw.hdl.spl_flow import partition
from xls_harness import REPO, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
EXT = HERE / "extern"
FILES = [str(HERE / "compose" / "hier_pkg.sv"), str(EXT / "ext_pkg.sv"),
         str(EXT / "fact_pkg.sv")]
FIFO = REPO / "src" / "rtl" / "fw_rv_fifo.sv"
DFM = REPO / "packages" / "python" / "bin" / "dfm"
needs = pytest.mark.skipif(not DFM.exists() or codegen_main() is None or opt_main() is None,
                           reason="needs dfm, opt_main and codegen_main")


def facts_of(shell, path):
    sh = shell
    *outer, leaf = path.split(".")
    for name in outer:
        sh = sh.nested(next(c for c in sh.children if c["name"] == name))
    return next(c for c in sh.children if c["name"] == leaf).get("facts")


# --------------------------------------------------------------- partition

def test_declared_facts_on_the_shell():
    p = partition(FILES, "rng_top", ["add_k"])
    assert [(f["kind"], f["value"]) for f in facts_of(p.shell, "q")] == [
        ("iface.latency", {"src": "in", "dst": "out", "min": 1, "max": 3}),
        ("area.estimate", {"value": 120, "unit": "cells", "source": "estimate"})]
    inner = facts_of(p.shell, "s.q")
    assert [f["kind"] for f in inner] == ["iface.latency", "iface.ii", "iface.capacity"]
    assert all(f["provenance"] == "declared" and f["unverified"] for f in inner)
    assert facts_of(p.shell, "s.x") is None


@pytest.mark.parametrize("top, msg, line", [
    ("null_top", "f.latency(...) is given a null port", 51),
    ("order_top", "latency: min 3 > max 1", 60),
])
def test_fact_errors_point_at_the_call(top, msg, line):
    with pytest.raises(FwHdlError) as e:
        partition(FILES, top, ["add_k"])
    assert msg in str(e.value) and f"fact_pkg.sv:{line}:" in str(e.value)


def test_sidecar(tmp_path):
    side = tmp_path / "q.facts.yaml"
    side.write_text("format: fw-hdl.facts\nversion: 1\nblocks:\n"
                    "  - class: q_side\n    facts:\n"
                    "      - {kind: latency, src: in, dst: out, max: 4}\n")
    p = partition(FILES, "side_top", ["add_k"], facts=[str(side)])
    assert facts_of(p.shell, "q")[0]["value"] == {"src": "in", "dst": "out", "max": 4, "min": 0}
    side.write_text(side.read_text().replace("q_side", "q_none"))
    with pytest.raises(Exception, match=r"design.facts: \['q_none'\] name no leaf child"):
        partition(FILES, "side_top", ["add_k"], facts=[str(side)])
    side.write_text(side.read_text().replace("q_none", "q_side").replace("src: in", "src: nope"))
    with pytest.raises(Exception, match="'nope' is not a port"):
        partition(FILES, "side_top", ["add_k"], facts=[str(side)])


def test_no_fact_keeps_the_note():
    """A wrapped child with no facts and no signature latency stays a note."""
    p = partition(FILES[:2], "ext_top1_t", ["add_k"])
    rep = latency.report(p.shell, {})
    assert rep.paths == []
    assert any(n.startswith("q_0: no timing for module") for n in rep.notes), rep.notes


# --------------------------------------------------------------- the flow

FLOW = """\
package:
  name: fr
  imports: [fw.hdl.spl, fw.hdl.knobs, fw.hdl.report, synth.xls, zuspec.xls]
  tasks:
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {base},
            include: [compose/hier_pkg.sv, extern/ext_pkg.sv, extern/fact_pkg.sv]}}
  - name: knob-file
    uses: std.FileSet
    with: {{type: fwKnobFile, include: [knobs.yaml]}}
  - {{name: knobs, uses: fw.hdl.knobs.Resolve, needs: [knob-file]}}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src, knobs]
    with: {{top: {top}, xls: [add_k]}}
  - {{name: rtl, uses: synth.xls.Codegen, needs: [part, knobs]}}
  - {{name: sig, uses: zuspec.xls.Signature, needs: [part, rtl]}}
  - {{name: top, uses: fw.hdl.spl.Integrate, needs: [part, sig, knobs]}}
  - {{name: lat, uses: fw.hdl.report.Latency, needs: [part, rtl]}}
  - {{name: all, needs: [top, lat]}}
"""

TB = """\
module xh_lat_tb;
  logic clk = 0, rst = 1;
  logic [7:0] in, out; logic in_vld = 0, in_rdy, out_vld, out_rdy = 1;
  int cyc = 0, tin = -1, tout = -1;
  {top} dut(.*);
  initial begin
    repeat (3) begin #5 clk = 1; #5 clk = 0; end
    rst = 0; in = 8'd5; in_vld = 1;
    while (tout < 0 && cyc < 200) begin
      #1;
      if (tin < 0 && in_vld && in_rdy) tin = cyc;
      if (tout < 0 && out_vld && out_rdy) begin
        tout = cyc;
        if (out != 8'd8) $display("BAD %0d", out);
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


def run_flow(tmp_path, top):
    (tmp_path / "knobs.yaml").write_text(
        f"design: {{top: {top}, xls: [add_k]}}\n"
        "xls: {default: {pipeline_stages: 1, delay_model: unit}}\n")
    (tmp_path / "flow.yaml").write_text(FLOW.format(base=HERE, top=top))
    r = subprocess.run([str(DFM), "run", "all"], cwd=tmp_path, capture_output=True, text=True,
                       env=dict(os.environ))
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    rd = tmp_path / "rundir"
    rep = json.loads((rd / "fr.lat" / "latency.json").read_text())
    (path,) = [p for p in rep["paths"] if (p["src"], p["dst"]) == ("in", "out")]
    srcs = sorted(rd.glob("fr.rtl/**/*.sv")) + sorted(rd.glob("fr.top/*.sv"))
    tb = tmp_path / "xh_lat_tb.sv"
    tb.write_text(TB.format(top=top))
    out = run_verilator([FIFO, *srcs, tb], "xh_lat_tb", tmp_path / "sim", with_lib=False)
    assert not [l for l in out if l.startswith("BAD")], out
    (measured,) = [int(l.split()[1]) for l in out if l.startswith("L ")]
    return rd, rep, path, measured


@needs
@pytest.mark.verilator
def test_fixed_path_through_wrapped_and_structural(tmp_path):
    rd, rep, path, measured = run_flow(tmp_path, "fix_top")
    assert rep["notes"] == []
    assert [(h["name"], h["source"]) for h in path["hops"] if h["what"] == "block"] == [
        ("s", "structural"), ("q", "declared")]
    assert path["min"] == path["max"] == path["cycles"] == measured
    assert path["unverified"]
    # The Partition task wrote the declared facts as an overlay.
    from zuspec.ir.core.results import load_store
    (bundle,) = (rd / "fr.part" / "facts").iterdir()
    store = load_store(str(bundle))
    (ov,) = store.overlays()
    assert ov.header.provenance == "declared"
    assert {f.kind for f in ov.facts()} == {"iface.latency", "iface.ii", "iface.capacity"}


@needs
@pytest.mark.verilator
def test_range_contains_the_measured_latency(tmp_path):
    _, rep, path, measured = run_flow(tmp_path, "rng_top")
    assert path["min"] <= measured <= path["max"]
    assert path["max"] - path["min"] == 2
    assert "*" in (tmp_path / "rundir" / "fr.lat" / "latency.md").read_text()
