"""fw_sram_fifo: an fw_channel bound to a RAM has fw_rv_fifo's handshake.

Both FIFOs, at the same DEPTH, take the same random traffic (phases that
fill, drain and stream, so the RAM fills, empties and is read and written in
the same cycle); every cycle in_rdy, out_vld and, while valid, out_data must
be equal. The RAM is fw_ram_1r1w_model. Yosys elaborates both.
"""
import re
import shutil
import subprocess

import pytest

from xls_harness import REPO, run_verilator
from fw_tools import have, tool

RTL = REPO / "src" / "rtl"
FILES = [RTL / "fw_rv_fifo.sv", RTL / "fw_sram_fifo.sv", RTL / "fw_ram_1r1w_model.sv"]
CYCLES = 3000


def lockstep_tb(depth: int, width: int = 10, seed: int = 1) -> str:
    return f"""\
module xh_sram_tb;
  localparam int W = {width}, D = {depth};
  logic clk = 0, rst = 1;
  logic [W-1:0] in_data, a_data, b_data;
  logic in_vld = 0, a_rdy, b_rdy, a_vld, b_vld, out_rdy = 0;
  logic [$clog2(D-1 > 1 ? D-1 : 2)-1:0] wa, ra;
  logic we, re;
  logic [W-1:0] wd, rd;
  int bad = 0, moved = 0, rams = 0, ph, pin, pout;
  fw_rv_fifo #(.WIDTH(W), .DEPTH(D)) a(.clk, .rst, .in_data, .in_vld, .in_rdy(a_rdy),
      .out_data(a_data), .out_vld(a_vld), .out_rdy);
  fw_sram_fifo #(.WIDTH(W), .DEPTH(D)) b(.clk, .rst, .in_data, .in_vld, .in_rdy(b_rdy),
      .out_data(b_data), .out_vld(b_vld), .out_rdy,
      .ram_wa(wa), .ram_we(we), .ram_wd(wd), .ram_ra(ra), .ram_re(re), .ram_rd(rd));
  fw_ram_1r1w_model #(.WIDTH(W), .WORDS(D-1)) m(.clk, .wa, .we, .wd, .ra, .re, .rd);
  initial begin
    void'($urandom({seed}));
    repeat (3) begin #5 clk = 1; #5 clk = 0; end
    rst = 0;
    for (int cyc = 0; cyc < {CYCLES}; cyc++) begin
      // phases of 100 cycles: fill (in busy, out idle), drain, stream, random
      // (assigned, not initialized: a declaration's initializer runs once)
      ph = (cyc / 100) % 4;
      pin = ph == 0 ? 9 : ph == 1 ? 1 : ph == 2 ? 10 : 5;
      pout = ph == 0 ? 1 : ph == 1 ? 9 : ph == 2 ? 10 : 5;
      in_vld = ($urandom % 10) < pin;
      in_data = W'($urandom);
      out_rdy = ($urandom % 10) < pout;
      #1;
      if (a_rdy !== b_rdy || a_vld !== b_vld || (a_vld && a_data !== b_data)) begin
        if (bad < 5) $display("M %0d rdy %b/%b vld %b/%b data %0d/%0d", cyc,
                              a_rdy, b_rdy, a_vld, b_vld, a_data, b_data);
        bad++;
      end
      if (a_vld && out_rdy) moved++;
      if (we) rams++;
      #4 clk = 1;
      #5 clk = 0;
    end
    $display("R bad=%0d moved=%0d ram_writes=%0d", bad, moved, rams);
    $display("X done");
    $finish;
  end
endmodule
"""


@pytest.mark.verilator
@pytest.mark.parametrize("depth,seed", [(3, 1), (4, 2), (5, 3), (8, 4), (17, 5)])
def test_same_handshake_as_rv_fifo(workdir, depth, seed):
    workdir.mkdir(parents=True, exist_ok=True)
    tb = workdir / "xh_sram_tb.sv"
    tb.write_text(lockstep_tb(depth, seed=seed))
    out = run_verilator([*FILES, tb], "xh_sram_tb", workdir, with_lib=False)
    r = next(m for l in out if (m := re.match(r"R bad=(\d+) moved=(\d+) ram_writes=(\d+)", l)))
    assert int(r[1]) == 0, "\n".join(l for l in out if l.startswith("M "))
    assert int(r[2]) > CYCLES // 3          # values moved
    assert int(r[3]) > 0                    # and some went through the RAM


def _yosys():
    return str(tool("yosys")) if have("yosys") else None


@pytest.mark.parametrize("depth", [3, 4, 16])
def test_yosys_elaborates(workdir, depth):
    yosys = _yosys()
    if yosys is None:
        pytest.skip("yosys not found")
    workdir.mkdir(parents=True, exist_ok=True)
    script = (f"read_verilog -sv {RTL / 'fw_sram_fifo.sv'}; "
              f"chparam -set DEPTH {depth} -set WIDTH 8 fw_sram_fifo; "
              f"synth -top fw_sram_fifo; check -assert")
    r = subprocess.run([yosys, "-q", "-p", script], cwd=workdir,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
