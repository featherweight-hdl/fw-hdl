"""read-gated MMIO FSM, generated from SV and simulated.

The reg_device shape: `if (ctrl.read().go) status.update(...)`.  Because the
readback is a registered value that settles a cycle after the change pulse, the
FSM registers the change (an `armed` flop) and samples `go` the next cycle.  We
prove the gate:

  - a write that changes CTRL but leaves go=0 (sets `arm`) must NOT set the flag;
  - a write that sets go=1 must set the flag.
"""
import subprocess
from pathlib import Path

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.mmio_synth import synth_mmio_design

REPO = Path(__file__).resolve().parents[3]
VERILATOR = REPO / "packages" / "verilator" / "bin" / "verilator"
GATED = REPO / "tests" / "mmio_gated"


_TB = """
module tb;
  logic clock = 0, reset = 1; always #5 clock = ~clock;
  logic [2:0]  s_addr = 0; logic s_wr = 0, s_rd = 0;
  logic [31:0] s_wdata = 0, s_rdata;
  gated_top dut (.clock, .reset, .s_addr, .s_wr, .s_wdata, .s_rd, .s_rdata);
  int errors = 0;
  task automatic chk(bit c, string m); if (!c) begin $display("FAIL: %s", m); errors++; end endtask

  task automatic bus_write(logic [2:0] a, logic [31:0] d);
    @(posedge clock); s_addr <= a; s_wdata <= d; s_wr <= 1;
    @(posedge clock); s_wr <= 0; s_wdata <= 0;
  endtask
  task automatic bus_read(logic [2:0] a, output logic [31:0] d);
    @(posedge clock); s_addr <= a; s_rd <= 1;
    @(posedge clock); d = s_rdata; s_rd <= 0;
  endtask

  logic [31:0] rd;
  initial begin
    repeat (3) @(posedge clock); reset = 0; @(posedge clock);

    // change CTRL but leave go=0 (set arm only) -> FSM wakes but the read-gate blocks
    bus_write(3'h0, 32'h2);            // arm=1, go=0
    repeat (3) @(posedge clock);
    bus_read(3'h4, rd);
    chk(rd[0] === 1'b0, "arm-only write (go=0) -> flag stays 0 (gate blocks)");

    // now set go=1 -> the read-gate passes -> flag latches
    bus_write(3'h0, 32'h3);            // arm=1, go=1
    repeat (3) @(posedge clock);
    bus_read(3'h4, rd);
    chk(rd[0] === 1'b1, "go=1 write -> flag set (gate passes)");

    if (errors == 0) $display("[mmio_gated] PASS");
    else             $display("[mmio_gated] FAIL (%0d errors)", errors);
    $finish;
  end
  initial begin #20000; $display("[mmio_gated] TIMEOUT"); $finish; end
endmodule
"""


def _design():
    rep = ErrorReporter()
    files = [str(GATED / f) for f in ("mmio_gated_pkg.sv", "mmio_gated_tb.sv")]
    d = synth_mmio_design(files, FlowConfig(), rep, top_name="gated_top")
    assert d is not None and not rep.has_errors(), rep.report()
    return d


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_gated_fsm_lints(tmp_path):
    d = _design()
    for fn, txt in d.files().items():
        (tmp_path / fn).write_text(txt)
    lint = subprocess.run(
        [str(VERILATOR), "--lint-only", "-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL",
         "--top-module", "gated_top", *d.files().keys()],
        cwd=tmp_path, capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout + lint.stderr


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_gated_fsm_simulates(tmp_path):
    d = _design()
    for fn, txt in d.files().items():
        (tmp_path / fn).write_text(txt)
    (tmp_path / "tb.sv").write_text(_TB)

    build = subprocess.run(
        [str(VERILATOR), "--binary", "--timing", "-j", "0", "-Wno-fatal",
         "--top-module", "tb", "-o", "simv", *d.files().keys(), "tb.sv"],
        cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / "obj_dir" / "simv")],
                         cwd=tmp_path, capture_output=True, text=True)
    assert "[mmio_gated] PASS" in run.stdout, run.stdout + run.stderr
