"""Run the fw_order_pkg SVUnit self-test (tests/order/flow.yaml)
through dfm. The fragment is wrapped in a throwaway package so the run does not
depend on loading the whole root flow."""
import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DFM = REPO / "packages" / "python" / "bin" / "dfm"


@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_fw_order_selftest(tmp_path):
    (tmp_path / "flow.yaml").write_text(
        "package:\n  name: ord\n  imports: [hdlsim, hdlsim.vlt, hdltest.svunit]\n"
        f"  fragments: [{HERE / 'flow.yaml'}]\n")
    r = subprocess.run([str(DFM), "run", "order.selftest"], cwd=tmp_path,
                       capture_output=True, text=True, env=dict(os.environ))
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    assert "SVUnit pass: 11 of 11 tests passing" in out, out[-3000:]


def test_fw_trace_feeds_canon(tmp_path):
    """fw_trace (SV) writes the trace format fw.hdl.verif.canon reads; the SV
    checker and the Python check agree on the same per-key stream."""
    import sys
    sys.path.insert(0, str(REPO / "tests" / "xls"))
    sys.path.insert(0, str(REPO / "python"))
    from xls_harness import have_verilator, run_verilator
    from fw.hdl.verif.canon import Rule, check, load_trace
    if not have_verilator():
        pytest.skip("needs verilator")
    tb = tmp_path / "tb.sv"
    trace = tmp_path / "t.jsonl"
    tb.write_text(f"""\
module tb;
  import fw_order_pkg::*;
  initial begin
    fw_trace t = new("{trace}");
    fw_order_check c = new("c", fw_order_rule::in_order_per_key());
    c.quiet = 1;
    for (longint i = 0; i < 6; i++) begin
      c.enter(i, i % 2, 0, i * 5, i); t.event_("req", "in", i, i, i % 2, 0, i * 5);
    end
    // odd keys first: legal per key
    for (longint j = 0; j < 6; j++) begin
      longint id;
      id = (j < 3) ? 2 * j + 1 : 2 * (j - 3);
      c.leave(id, id * 5, 10 + j); t.event_("rsp", "out", 10 + j, id, id % 2, 0, id * 5);
    end
    c.finish();
    t.close();
    $display("E %0d", c.n_errors);
    $display("X done");
    $finish;
  end
endmodule
""")
    out = run_verilator([REPO / "src" / "std" / "order" / "fw_order_pkg.sv", tb], "tb",
                        tmp_path / "sim", with_lib=False)
    assert "E 0" in out
    events = load_trace(trace)
    assert len(events) == 12
    assert check(events, Rule(per_key=True)) == []
    assert check(events, Rule()) != []          # not legal as a total order
