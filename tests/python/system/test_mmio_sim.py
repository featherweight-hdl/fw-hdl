"""F-A5: the MMIO design, generated entirely from SV and simulated.

The front-end-driven analogue of ``test_engine_regblock_sim`` — but here the FSM
SPL is **not** hand-built: ``fw-hdl`` parses ``mmio_fsm.sv`` and produces all
modules (FSM, regblock, structural top) through the real F-A1..F-A4 path.  We then
lint and simulate:

    bus write to the watched register (CTRL) -> regblock change pulse -> FSM Mealy
    hwif pulse -> STATUS.flag latches; a write to the unwatched STATUS does NOT
    wake the FSM.
"""
import subprocess
from pathlib import Path

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.mmio_synth import synth_mmio_design

REPO = Path(__file__).resolve().parents[3]
VERILATOR = REPO / "packages" / "verilator" / "bin" / "verilator"
MMIO = REPO / "tests" / "mmio"


_TB = """
module tb;
  logic clock = 0, reset = 1; always #5 clock = ~clock;
  logic [2:0]  s_addr = 0; logic s_wr = 0, s_rd = 0;
  logic [31:0] s_wdata = 0, s_rdata;
  mmio_top dut (.clock, .reset, .s_addr, .s_wr, .s_wdata, .s_rd, .s_rdata);
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

    bus_read(3'h4, rd);                 // STATUS
    chk(rd[0] === 1'b0, "flag starts 0");

    // write the UNWATCHED status reg (RO to sw): no effect, must NOT wake the FSM
    bus_write(3'h4, 32'h1);
    bus_read(3'h4, rd);
    chk(rd[0] === 1'b0, "unwatched write -> FSM NOT woken (flag still 0)");

    // write the WATCHED ctrl reg: wakes the FSM -> Mealy hwif pulse -> flag latches
    bus_write(3'h0, 32'h1);
    bus_read(3'h4, rd);
    chk(rd[0] === 1'b1, "ctrl write -> FSM pulsed STATUS.flag");

    if (errors == 0) $display("[mmio] PASS");
    else             $display("[mmio] FAIL (%0d errors)", errors);
    $finish;
  end
  initial begin #20000; $display("[mmio] TIMEOUT"); $finish; end
endmodule
"""


def _design():
    rep = ErrorReporter()
    files = [str(MMIO / f) for f in ("mmio_pkg.sv", "mmio_tb.sv")]
    d = synth_mmio_design(files, FlowConfig(), rep, top_name="mmio_top")
    assert d is not None and not rep.has_errors(), rep.report()
    return d


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_generated_design_lints(tmp_path):
    d = _design()
    for fn, txt in d.files().items():
        (tmp_path / fn).write_text(txt)
    lint = subprocess.run(
        [str(VERILATOR), "--lint-only", "-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL",
         "--top-module", "mmio_top", *d.files().keys()],
        cwd=tmp_path, capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout + lint.stderr


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_generated_design_simulates(tmp_path):
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
    assert "[mmio] PASS" in run.stdout, run.stdout + run.stderr
