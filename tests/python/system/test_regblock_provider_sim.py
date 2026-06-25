"""M8b: behavioral sim of a reflected (provider) register on the generated RTL.

Proves the reflect field has NO storage: its readback follows the provider input
*combinationally* (changes with no clock edge), while a normal software register
in the same block still stores/round-trips.
"""
import subprocess
from pathlib import Path

import pytest

from fw.hdl.emit.regblock import emit_regblock
from fw.hdl.regmap import RegBlock, Register, RegField, RegUsage

REPO = Path(__file__).resolve().parents[3]
VERILATOR = REPO / "packages" / "verilator" / "bin" / "verilator"


def _block():
    ctrl = Register("ctrl", 0x0, 32, sw_wmask=0x1, fields=[
        RegField("en", 0, 1, sw_write=True, hw_write=False, rclr=False)])
    status = Register("status", 0x4, 32, hw_wmask=0xffffffff, fields=[
        RegField("val", 0, 32, sw_write=False, hw_write=True, rclr=False)])
    return RegBlock("dev", registers=[ctrl, status], size=0x8)


_TB = """
module tb;
  logic clock = 0, reset = 1;
  always #5 clock = ~clock;
  logic [2:0]  s_addr = 0;
  logic        s_wr = 0, s_rd = 0;
  logic [31:0] s_wdata = 0, s_rdata;
  logic [0:0]  hwif_out_ctrl__en;
  logic [31:0] hwif_in_status_rdata = 0;          // the provider's on_read output

  dev_regblock dut (
    .clock, .reset, .s_addr, .s_wr, .s_wdata, .s_rd, .s_rdata,
    .hwif_out_ctrl__en, .hwif_in_status_rdata);

  int errors = 0;
  task automatic chk(bit c, string m); if (!c) begin $display("FAIL: %s", m); errors++; end endtask

  initial begin
    repeat (3) @(posedge clock); reset = 0; @(posedge clock);

    // address the reflected register; its readback follows the provider input
    @(posedge clock); s_addr <= 3'h4; s_rd <= 1; s_wr <= 0;
    @(posedge clock);
    hwif_in_status_rdata = 32'hDEAD_BEEF; #1
      chk(s_rdata === 32'hDEAD_BEEF, "reflect follows provider");
    hwif_in_status_rdata = 32'h0BAD_F00D; #1
      chk(s_rdata === 32'h0BAD_F00D, "reflect is combinational (no clock, no storage)");

    // a normal software register in the same block still stores
    @(posedge clock); s_addr <= 3'h0; s_wdata <= 32'h1; s_wr <= 1; s_rd <= 0;
    @(posedge clock); s_wr <= 0;
    @(posedge clock); s_addr <= 3'h0; s_rd <= 1;
    @(posedge clock); #1 chk(s_rdata[0] === 1'b1, "ctrl still round-trips");

    if (errors == 0) $display("[provider_sim] PASS"); else $display("[provider_sim] FAIL");
    $finish;
  end
  initial begin #10000; $display("[provider_sim] TIMEOUT"); $finish; end
endmodule
"""


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_reflected_register_has_no_storage(tmp_path):
    (tmp_path / "rb.sv").write_text(
        emit_regblock(_block(), usage=RegUsage(providers=[0x4])))
    (tmp_path / "tb.sv").write_text(_TB)
    build = subprocess.run(
        [str(VERILATOR), "--binary", "--timing", "-j", "0", "-Wno-fatal",
         "--top-module", "tb", "-o", "simv", "rb.sv", "tb.sv"],
        cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / "obj_dir" / "simv")],
                         cwd=tmp_path, capture_output=True, text=True)
    assert "[provider_sim] PASS" in run.stdout, run.stdout + run.stderr
