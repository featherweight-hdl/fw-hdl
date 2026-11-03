"""The response-tracker reference design (examples/resp_tracker), stage 1.

One source, many schedules (W1 exit, RQ-S2/S3):
* each knob set k0-k2 builds with fw-hdl tasks only, the boundary checks at
  error severity;
* the RTL of every knob set and the class model give the same stream, as the
  in-order contract compares them (RQ-V2, RQ-V4), and match the reference;
* the generated latency table equals the latency measured on the RTL;
* k3's contract is rejected before codegen.
"""
import json
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

import zuspec.ir.core as ir
from fw.hdl.verif.canon import Event, Rule, check, compare
from fw.hdl.xls_flow import sv_to_structure
from xls_harness import proc_testbench, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXAMPLE = REPO / "examples" / "resp_tracker"
DFM = REPO / "packages" / "python" / "bin" / "dfm"

needs = pytest.mark.skipif(not DFM.exists() or codegen_main() is None or opt_main() is None,
                           reason="needs dfm, opt_main and codegen_main")

#: First-value latency per knob set (examples/resp_tracker/knobs).
EXPECTED_LATENCY = {"k0": 1, "k1": 3, "k2": 2}
N = 200


def reference(addrs):
    return [((i % 16) << 12) | ((a * 3) & 0xfff) for i, a in enumerate(addrs)]


def stimulus(seed):
    rng = random.Random(seed)
    return rng.sample(range(256), N)        # distinct addresses identify each item


def trace(addrs, outs):
    """In events carry the reference response; out events are identified by
    their address (data / 3), so loss, duplication, reordering and corruption
    all show."""
    want = reference(addrs)
    ev = [Event("req", "in", i, a, data=want[i]) for i, a in enumerate(addrs)]
    ev += [Event("rsp", "out", N + j, ((v & 0xfff) // 3), data=v) for j, v in enumerate(outs)]
    return ev


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Every knob set built once, from a copy of the example."""
    root = tmp_path_factory.mktemp("rt")
    out = {}
    for kset in ("k0", "k1", "k2", "k3"):
        d = root / kset
        shutil.copytree(EXAMPLE, d, ignore=shutil.ignore_patterns("rundir"))
        r = subprocess.run([str(DFM), "run", "all", "-D", f"kset={kset}"], cwd=d,
                           capture_output=True, text=True, env=dict(os.environ))
        out[kset] = (d, r.returncode, " ".join((r.stdout + r.stderr).split()))
    return out


def _outputs(rd: Path, task: str):
    return json.loads((rd / task / f"{task}.exec_data.json").read_text())["output"]["output"]


def _files(rd: Path, task: str, ft: str):
    return [Path(fs["basedir"]) / f for fs in _outputs(rd, task)
            if fs["filetype"] == ft for f in fs["files"]]


LAT_TB = """\
module xh_lat_tb;
  logic clk = 0, rst = 1;
  logic [7:0] req; logic [15:0] rsp;
  logic req_vld = 0, req_rdy, rsp_vld, rsp_rdy = 1;
  int cyc = 0, tin = -1, tout = -1;
  rt_top dut(.*);
  initial begin
    repeat (3) begin #5 clk = 1; #5 clk = 0; end
    rst = 0; req = 8'd9; req_vld = 1;
    while (tout < 0 && cyc < 200) begin
      #1;
      if (tin < 0 && req_vld && req_rdy) tin = cyc;
      if (tout < 0 && rsp_vld && rsp_rdy) tout = cyc;
      #4 clk = 1; #5 clk = 0;
      if (tin >= 0) req_vld = 0;
      cyc++;
    end
    $display("L %0d", tout - tin);
    $display("X done");
    $finish;
  end
endmodule
"""


@needs
@pytest.mark.verilator
@pytest.mark.parametrize("kset", ["k0", "k1", "k2"])
def test_knob_set_builds_and_matches(built, tmp_path, kset):
    d, rc, log = built[kset]
    assert rc == 0, log[-3000:]
    rd = d / "rundir"
    rtl = _files(rd, "resp_tracker.top", "systemVerilogSource")
    (sig_path,) = _files(rd, "resp_tracker.top", "blockSignature")
    sig = ir.load_signature(str(sig_path))

    # RTL view, randomly throttled
    addrs = stimulus(seed=int(kset[1:]) + 1)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(sig, {"req": addrs}, seed=3))
    out = run_verilator(rtl + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    rtl_outs = [int(l.split()[3], 16) for l in out if l.startswith("O rsp ")]

    # class-model view, same stimulus
    pkg = _files(rd, "resp_tracker.knobs", "systemVerilogSource")
    files = [str(p) for p in pkg] + [str(d / "src" / "rt_pkg.sv")]
    comp = sv_to_structure(files, "rt_top").component
    mtb = tmp_path / "xh_proc_tb.sv"
    mtb.write_text(proc_testbench(["rt_pkg"], "rt_top", comp, {"req": addrs}))
    mout = run_verilator(files + [mtb], "xh_proc_tb", tmp_path / "model")
    model_outs = [int(l.split()[3], 16) for l in mout if l.startswith("O rsp ")]

    rule = Rule()                                   # responses in request order
    t_rtl, t_model = trace(addrs, rtl_outs), trace(addrs, model_outs)
    assert check(t_rtl, rule) == []
    assert compare(t_model, t_rtl, rule, names=("model", "rtl")) == []

    # the generated latency table equals simulation
    rep = json.loads((rd / "resp_tracker.latency" / "latency.json").read_text())
    (path,) = [p for p in rep["paths"] if (p["src"], p["dst"]) == ("req", "rsp")]
    ltb = tmp_path / "xh_lat_tb.sv"
    ltb.write_text(LAT_TB)
    lout = run_verilator(rtl + [ltb], "xh_lat_tb", tmp_path / "lat", with_lib=False)
    (measured,) = [int(l.split()[1]) for l in lout if l.startswith("L ")]
    assert path["cycles"] == measured == EXPECTED_LATENCY[kset]


@needs
def test_unmeetable_contract_is_rejected_before_codegen(built):
    d, rc, log = built["k3"]
    assert rc != 0 and "cannot be met" in log, log[-3000:]
    assert not list((d / "rundir").glob("resp_tracker.rtl/*.sv"))
