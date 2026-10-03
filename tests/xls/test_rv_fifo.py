"""INT-2 (xls-phase2.md): fw_rv_fifo, the RTL form of fw_channel, on Verilator.

Random valid on the input and random ready on the output: the output stream must
equal the input stream, the FIFO must never hold more than DEPTH values, and
with the output stalled it must accept exactly DEPTH values (DEPTH == 0: none,
it is a wire).
"""
import re
from pathlib import Path

import pytest

from xls_harness import REPO, run_verilator

FIFO = REPO / "src" / "rtl" / "fw_rv_fifo.sv"
N = 200


def fifo_tb(depth: int, width: int = 12) -> str:
    return f"""\
module xh_fifo_tb;
  logic clk = 0, rst = 1;
  logic [{width-1}:0] in_data, out_data;
  logic in_vld = 0, in_rdy, out_vld, out_rdy = 0;
  int sent = 0, got = 0, stalled_accepts = 0, cycle = 0;
  fw_rv_fifo #(.WIDTH({width}), .DEPTH({depth})) dut(.*);
  initial begin
    void'($urandom(7));
    repeat (3) begin #5 clk = 1; #5 clk = 0; end
    rst = 0;
    // 1. output stalled: how many values does it take?
    in_vld = 1; out_rdy = 0;
    for (int i = 0; i < {depth} + 3; i++) begin
      in_data = {width}'(1000 + i);
      #1;
      if (in_vld && in_rdy) stalled_accepts++;
      #4 clk = 1;
      #5 clk = 0;
    end
    $display("S %0d", stalled_accepts);
    // drain what it took
    in_vld = 0; out_rdy = 1;
    repeat ({depth} + 2) begin
      #1;
      if (out_vld && out_rdy) $display("O %0d", out_data);
      #4 clk = 1; #5 clk = 0;
    end
    // 2. random traffic: drive, let it settle, sample both handshakes, clock
    while (got < {N} && cycle < 20000) begin
      bit fire_in, fire_out;
      if (!in_vld && sent < {N} && ($urandom % 3) != 0) begin
        in_vld = 1; in_data = {width}'(sent * 37 + 5);
      end
      out_rdy = ($urandom % 3) != 0;
      #1;
      fire_in  = in_vld && in_rdy;
      fire_out = out_vld && out_rdy;
      if (fire_out) begin $display("O %0d", out_data); got++; end
      #4 clk = 1;
      #5 clk = 0;
      if (fire_in) begin sent++; in_vld = 0; end
      cycle++;
    end
    $display("X done");
    $finish;
  end
endmodule
"""


@pytest.mark.verilator
@pytest.mark.parametrize("depth", [0, 1, 2, 5])
def test_fw_rv_fifo(workdir, depth):
    workdir.mkdir(parents=True, exist_ok=True)
    tb = workdir / "xh_fifo_tb.sv"
    tb.write_text(fifo_tb(depth))
    out = run_verilator([FIFO, tb], "xh_fifo_tb", workdir, with_lib=False)
    stalled = [int(m[1]) for l in out if (m := re.match(r"S (\d+)$", l))]
    assert stalled == [depth]
    got = [int(m[1]) for l in out if (m := re.match(r"O (\d+)$", l))]
    assert got[:depth] == [1000 + i for i in range(depth)]       # the stalled values drain first
    assert got[depth:] == [(i * 37 + 5) & 0xfff for i in range(N)]
