"""Phase 1 K2-K4, K6: the ready/valid kit in src/std/rv.

* the kit test (driver -> initiator -> pins -> target -> sink, monitor tapping)
  at a 32-bit, an 8-bit and a struct payload, with backpressure on the pins;
* the put/get adapters under backpressure: no beat lost or duplicated;
* the run-time knobs (depth, max_gap) and the monitor's first-valid events;
* the same test through the dfm fragment (tests/rv_proto/flow.yaml);
* the synthesizable cores (width W, not `type T`: yosys has no type
  parameters) elaborate in yosys at two widths.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from fw_tools import tool, have

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SRC = REPO / "src"
RV = SRC / "std" / "rv"
DFM = tool("dfm")
sys.path.insert(0, str(REPO / "tests" / "xls"))
from xls_harness import have_verilator, run_verilator  # noqa: E402

RV_FILES = [RV / f for f in (
    "fw_rv_pkg.sv",
    "fw_rv_initiator_xtor_if.sv", "fw_rv_initiator_xtor_core.sv", "fw_rv_initiator_xtor.sv",
    "fw_rv_target_xtor_if.sv", "fw_rv_target_xtor_core.sv", "fw_rv_target_xtor.sv",
    "fw_rv_monitor_xtor_if.sv", "fw_rv_monitor_xtor_core.sv", "fw_rv_monitor_xtor.sv")]
CORES = [RV / f"fw_rv_{r}_xtor_core.sv" for r in ("initiator", "target", "monitor")]

needs_vlt = pytest.mark.skipif(not have_verilator(), reason="needs verilator")


def _sim(tmp_path, tb, top, defines=()):
    return run_verilator([SRC / "fw_root.sv", *RV_FILES, HERE / "rv_proto_pkg.sv", HERE / tb],
                         top, tmp_path,
                         extra=[f"+incdir+{RV}", f"+incdir+{HERE}", *(f"+define+{d}" for d in defines)])


@needs_vlt
@pytest.mark.parametrize("defines", [(), ("RV_W8",), ("RV_STRUCT",)], ids=["w32", "w8", "struct"])
def test_kit_round_trip(tmp_path, defines):
    out = _sim(tmp_path, "rv_proto_tb.sv", "rv_proto_tb", defines)
    assert "[rv_proto] PASS" in out, "\n".join(out[-40:])
    (stalls,) = [int(l.split("=")[1]) for l in out if l.startswith("[rv_proto] stalls=")]
    assert stalls > 0


@needs_vlt
def test_put_get_adapters_under_backpressure(tmp_path):
    out = run_verilator([SRC / "fw_root.sv", *RV_FILES, HERE / "rv_adapter_tb.sv"],
                        "rv_adapter_tb", tmp_path, extra=[f"+incdir+{RV}"])
    assert "[rv_adapter] PASS" in out, "\n".join(out[-40:])


@needs_vlt
def test_runtime_knobs(tmp_path):
    """depth and max_gap on the initiator and target; the monitor's first-valid events."""
    out = run_verilator([SRC / "fw_root.sv", *RV_FILES, HERE / "rv_knobs_tb.sv"],
                        "rv_knobs_tb", tmp_path, extra=[f"+incdir+{RV}"])
    assert "[rv_knobs] PASS" in out, "\n".join(out[-40:])


@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_kit_through_dfm_fragment(tmp_path):
    (tmp_path / "flow.yaml").write_text(
        "package:\n  name: rvk\n  imports: [hdlsim, hdlsim.vlt]\n"
        f"  fragments: [{SRC / 'flow.yaml'}, {HERE / 'flow.yaml'}]\n")
    r = subprocess.run([str(DFM), "run", "rv_proto.rv-proto"], cwd=tmp_path,
                       capture_output=True, text=True, env=dict(os.environ))
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    log = "".join(p.read_text() for p in (tmp_path / "rundir").rglob("*.log"))
    assert "[rv_proto] PASS" in out + log, out[-3000:]


@pytest.mark.skipif(not have("yosys"), reason="needs yosys")
@pytest.mark.parametrize("width", [8, 32])
def test_cores_synthesize(tmp_path, width):
    yosys = str(tool("yosys"))
    script = "".join(f"read_verilog -sv {c}\n" for c in CORES)
    script += "".join(f"chparam -set W {width} {c.stem}\n" for c in CORES)
    script += "hierarchy -check\nproc\nopt\nstat\n"
    (tmp_path / "s.ys").write_text(script)
    r = subprocess.run([yosys, "-q", "-s", str(tmp_path / "s.ys")], capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]


@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_cores_prove(tmp_path):
    """SBY BMC over the two cores back to back (tests/rv_proto/formal)."""
    (tmp_path / "flow.yaml").write_text(
        "package:\n  name: rvf\n  imports: [formal]\n"
        f"  fragments: [{SRC / 'flow.yaml'}, {HERE / 'formal' / 'flow.yaml'}]\n")
    r = subprocess.run([str(DFM), "run", "rv_formal.fv"], cwd=tmp_path,
                       capture_output=True, text=True, env=dict(os.environ))
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    # A proof with no properties passes too: check they reached the model.
    (il,) = (tmp_path / "rundir").rglob("model/design.il")
    assert il.read_text().count("cell $check") >= 5   # assert, assume, cover
