"""The response-tracker reference design (examples/resp_tracker), stage 1.

One source, many schedules:
* each knob set k0-k2 builds with fw-hdl tasks only, the boundary checks at
  error severity;
* the RTL of every knob set and the class model give the same stream, as the
  in-order contract compares them, and match the reference;
* the generated latency table equals the latency measured on the RTL;
* k3's contract is rejected before codegen.

Both forms of the source give these results: rt_pkg.sv (run() processes) and
rt_step_pkg.sv (cycle steps).
"""
import json
import os
import random
import shutil
import subprocess
from pathlib import Path
from fw_tools import tool

import pytest

import zuspec.ir.core as ir
from fw.hdl.verif.canon import Event, Rule, check, compare
from fw.hdl.xls_flow import sv_to_structure
from xls_harness import proc_testbench, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EXAMPLE = REPO / "examples" / "resp_tracker"
DFM = tool("dfm")

needs = pytest.mark.skipif(not DFM.exists() or codegen_main() is None or opt_main() is None,
                           reason="needs dfm, opt_main and codegen_main")

#: First-value latency per source form and knob set (examples/resp_tracker/knobs).
#: The step form runs k1 and k2's schedules with a two-deep queue (k1s, k2s):
#: a step never waits, so its queue must hold what it sends every cycle.
EXPECTED_LATENCY = {
    "rt_pkg": {"k0": 1, "k1": 3, "k2": 2},
    "rt_step_pkg": {"k0": 1, "k1s": 3, "k2s": 3},
}
CASES = [(f, k) for f, ks in EXPECTED_LATENCY.items() for k in ks]
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
    """``built(form, kset)``: that knob set built once, from a copy of the
    example: (directory, return code, log)."""
    root = tmp_path_factory.mktemp("rt")
    done = {}

    def get(form, kset):
        if (form, kset) not in done:
            d = root / form / kset
            shutil.copytree(EXAMPLE, d, ignore=shutil.ignore_patterns("rundir"))
            r = subprocess.run([str(DFM), "run", "all", "-D", f"kset={kset}",
                                "-D", f"form={form}"],
                               cwd=d, capture_output=True, text=True, env=dict(os.environ))
            done[form, kset] = (d, r.returncode, " ".join((r.stdout + r.stderr).split()))
        return done[form, kset]
    return get


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
@pytest.mark.parametrize("form,kset", CASES, ids=[f"{f}-{k}" for f, k in CASES])
def test_knob_set_builds_and_matches(built, tmp_path, form, kset):
    d, rc, log = built(form, kset)
    assert rc == 0, log[-3000:]
    rd = d / "rundir"
    rtl = _files(rd, "resp_tracker.top", "systemVerilogSource")
    (sig_path,) = _files(rd, "resp_tracker.top", "blockSignature")
    sig = ir.load_signature(str(sig_path))

    # RTL view, randomly throttled
    addrs = stimulus(seed=int(kset[1]) + 1)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(sig, {"req": addrs}, seed=3))
    out = run_verilator(rtl + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    rtl_outs = [int(l.split()[3], 16) for l in out if l.startswith("O rsp ")]

    # class-model view, same stimulus
    pkg = _files(rd, "resp_tracker.knobs", "systemVerilogSource")
    files = [str(p) for p in pkg] + [str(d / "src" / f"{form}.sv")]
    comp = sv_to_structure(files, "rt_top").component
    mtb = tmp_path / "xh_proc_tb.sv"
    mtb.write_text(proc_testbench([form], "rt_top", comp, {"req": addrs},
                                  clocked=form == "rt_step_pkg"))
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
    assert path["cycles"] == measured == EXPECTED_LATENCY[form][kset]


@needs
@pytest.mark.verilator
def test_step_form_needs_a_deep_enough_queue(built, tmp_path):
    """k1's one-deep queue under the step form: a value is sent every cycle
    and none can wait, so both views report the same credit violation."""
    d, rc, log = built("rt_step_pkg", "k1")
    assert rc == 0, log[-3000:]
    rd = d / "rundir"
    rtl = _files(rd, "resp_tracker.top", "systemVerilogSource")
    (sig_path,) = _files(rd, "resp_tracker.top", "blockSignature")
    addrs = stimulus(seed=5)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(ir.load_signature(str(sig_path)), {"req": addrs}, seed=3,
                                throttle=1000))
    out = run_verilator(rtl + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False,
                        allow_stop=True, extra=["--assert", "+define+ASSERT_ON"])
    assert any("offered while full" in l for l in out), "\n".join(out[-10:])
    pkg = _files(rd, "resp_tracker.knobs", "systemVerilogSource")
    files = [str(p) for p in pkg] + [str(d / "src" / "rt_step_pkg.sv")]
    comp = sv_to_structure(files, "rt_top").component
    mtb = tmp_path / "xh_proc_tb.sv"
    mtb.write_text(proc_testbench(["rt_step_pkg"], "rt_top", comp, {"req": addrs},
                                  clocked=True))
    mout = run_verilator(files + [mtb], "xh_proc_tb", tmp_path / "model", allow_stop=True)
    assert any("credit violation" in l for l in mout), "\n".join(mout[-10:])


@needs
@pytest.mark.parametrize("form", list(EXPECTED_LATENCY))
def test_unmeetable_contract_is_rejected_before_codegen(built, form):
    d, rc, log = built(form, "k3")
    assert rc != 0 and "cannot be met" in log, log[-3000:]
    assert not list((d / "rundir").glob("resp_tracker.rtl/*.sv"))
