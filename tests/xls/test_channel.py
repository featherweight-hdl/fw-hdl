"""ST-1 (xls-phase2.md): fw_channel #(T, DEPTH) on Verilator.

A producer puts 0..N-1 as fast as the channel lets it; the consumer takes one
value every 100 time units. Values must arrive in order, and each put must
return exactly when DEPTH says it may:

* DEPTH >= 1: put i returns at 100 * max(0, i - DEPTH + 1)
  (the first DEPTH go straight in, then one per get);
* DEPTH == 0: put i returns at 100 * (i + 1), when get i takes it.
"""
import re

import pytest

from xls_harness import run_verilator

N = 6


def channel_tb(depth: int) -> str:
    return f"""\
module xh_chan_tb;
  import fw_hdl_pkg::*;
  import fw_std_pkg::*;
  fw_channel #(bit [7:0], {depth}) ch;
  initial begin
    ch = new("ch", null);
    fork
      begin
        for (int i = 0; i < {N}; i++) begin
          ch.put_ex.put(8'(i));
          $display("P %0d %0t", i, $time);
        end
      end
      begin
        for (int i = 0; i < {N}; i++) begin
          bit [7:0] v;
          #100;
          ch.get_ex.get(v);
          $display("G %0d %0t", v, $time);
        end
      end
    join
    $display("X done");
    $finish;
  end
endmodule
"""


@pytest.mark.verilator
@pytest.mark.parametrize("depth", [0, 1, 3])
def test_fw_channel_depth(workdir, depth):
    tb = workdir / "xh_chan_tb.sv"
    workdir.mkdir(parents=True, exist_ok=True)
    tb.write_text(channel_tb(depth))
    out = run_verilator([tb], "xh_chan_tb", workdir)
    puts = {int(m[1]): int(m[2]) for l in out if (m := re.match(r"P (\d+) (\d+)$", l))}
    gets = [(int(m[1]), int(m[2])) for l in out if (m := re.match(r"G (\d+) (\d+)$", l))]
    assert [v for v, _ in gets] == list(range(N))
    assert [t for _, t in gets] == [100 * (i + 1) for i in range(N)]
    want = {i: 100 * (i + 1) if depth == 0 else 100 * max(0, i - depth + 1)
            for i in range(N)}
    assert puts == want, f"DEPTH={depth}: put return times {puts}, expected {want}"
