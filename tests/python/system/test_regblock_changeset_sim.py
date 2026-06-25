"""M7: behavioral sim of the watch-set change pulse on the generated RTL.

Proves the wake is on SOFTWARE writes to members only:
  - sw write to a member        -> set_changed pulses
  - hardware update of a member  -> NO pulse (the waiter's own status update would
                                    otherwise self-wake it -- the whole point)
  - sw write to a non-member     -> no pulse
  - sw read of a member          -> no pulse
"""
import subprocess
from pathlib import Path

import pytest

from fw.hdl.emit.regblock import emit_regblock
from fw.hdl.regmap import RegBlock, Register, RegField, RegUsage

REPO = Path(__file__).resolve().parents[3]
VERILATOR = REPO / "packages" / "verilator" / "bin" / "verilator"


def _block():
    # r0 (member): a sw config bit + a hw status bit; r1 (non-member): sw bit.
    r0 = Register("r0", 0x0, 32, reset=0, sw_wmask=0x1, hw_wmask=0x2, fields=[
        RegField("cfg", 0, 1, sw_write=True,  hw_write=False, rclr=False),
        RegField("st",  1, 1, sw_write=False, hw_write=True,  rclr=False),
    ])
    r1 = Register("r1", 0x4, 32, reset=0, sw_wmask=0x1, fields=[
        RegField("cfg", 0, 1, sw_write=True, hw_write=False, rclr=False),
    ])
    return RegBlock("mini", registers=[r0, r1], size=0x8)


_TB = """
module tb;
  logic clock = 0, reset = 1;
  always #5 clock = ~clock;
  logic [2:0]  s_addr = 0;
  logic        s_wr = 0, s_rd = 0;
  logic [31:0] s_wdata = 0, s_rdata;
  logic [0:0]  hwif_in_r0__st_next = 0, hwif_in_r0__st_we = 0;
  logic [0:0]  hwif_out_r0__cfg, hwif_out_r0__st, hwif_out_r1__cfg;
  logic        ws_changed;

  mini_regblock dut (
    .clock, .reset, .s_addr, .s_wr, .s_wdata, .s_rd, .s_rdata,
    .hwif_in_r0__st_next, .hwif_in_r0__st_we,
    .hwif_out_r0__cfg, .hwif_out_r0__st, .hwif_out_r1__cfg, .ws_changed);

  int errors = 0;
  task automatic chk(bit c, string m); if (!c) begin $display("FAIL: %s", m); errors++; end endtask

  initial begin
    repeat (3) @(posedge clock); reset = 0; @(posedge clock);

    // sw write to member r0 -> pulse
    s_addr = 0; s_wdata = 1; s_wr = 1; #1 chk(ws_changed === 1'b1, "sw write member wakes");
    @(posedge clock); s_wr = 0; #1 chk(ws_changed === 1'b0, "pulse clears when idle");

    // hardware update of member r0 -> NO pulse (self-wake elimination)
    s_addr = 0; hwif_in_r0__st_next = 1; hwif_in_r0__st_we = 1;
    #1 chk(ws_changed === 1'b0, "hw update of member does NOT wake");
    @(posedge clock); hwif_in_r0__st_we = 0;

    // sw write to NON-member r1 -> no pulse
    s_addr = 4; s_wdata = 1; s_wr = 1; #1 chk(ws_changed === 1'b0, "non-member write does not wake");
    @(posedge clock); s_wr = 0;

    // sw read of member r0 -> no pulse (read, not write)
    s_addr = 0; s_rd = 1; #1 chk(ws_changed === 1'b0, "member read does not wake");
    @(posedge clock); s_rd = 0;

    if (errors == 0) $display("[changeset_sim] PASS"); else $display("[changeset_sim] FAIL");
    $finish;
  end
  initial begin #10000; $display("[changeset_sim] TIMEOUT"); $finish; end
endmodule
"""


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_change_pulse_is_software_write_only(tmp_path):
    usage = RegUsage(change_sets={"ws": [0x0]})        # watch only r0
    (tmp_path / "rb.sv").write_text(emit_regblock(_block(), usage=usage))
    (tmp_path / "tb.sv").write_text(_TB)

    build = subprocess.run(
        [str(VERILATOR), "--binary", "--timing", "-j", "0", "-Wno-fatal",
         "--top-module", "tb", "-o", "simv", "rb.sv", "tb.sv"],
        cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / "obj_dir" / "simv")],
                         cwd=tmp_path, capture_output=True, text=True)
    assert "[changeset_sim] PASS" in run.stdout, run.stdout + run.stderr
