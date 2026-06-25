"""F-A5 / multi-FSM: two FSMs driven from ONE register model, simulated.

Proves the architecture the user called out (e.g. an FSM per DMA channel): the
front end emits the regblock once and wires several FSMs to it.  Independence: a
write to CTRL_A wakes only FSM A (sets STATUS_A.flag), not FSM B; a write to
CTRL_B wakes only FSM B.
"""
import subprocess
from pathlib import Path

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.mmio_synth import synth_mmio_design

REPO = Path(__file__).resolve().parents[3]
VERILATOR = REPO / "packages" / "verilator" / "bin" / "verilator"
MMIO_MULTI = REPO / "tests" / "mmio_multi"


_TB = """
module tb;
  logic clock = 0, reset = 1; always #5 clock = ~clock;
  logic [3:0]  s_addr = 0; logic s_wr = 0, s_rd = 0;
  logic [31:0] s_wdata = 0, s_rdata;
  multi_top dut (.clock, .reset, .s_addr, .s_wr, .s_wdata, .s_rd, .s_rdata);
  int errors = 0;
  task automatic chk(bit c, string m); if (!c) begin $display("FAIL: %s", m); errors++; end endtask

  task automatic bus_write(logic [3:0] a, logic [31:0] d);
    @(posedge clock); s_addr <= a; s_wdata <= d; s_wr <= 1;
    @(posedge clock); s_wr <= 0; s_wdata <= 0;
  endtask
  task automatic bus_read(logic [3:0] a, output logic [31:0] d);
    @(posedge clock); s_addr <= a; s_rd <= 1;
    @(posedge clock); d = s_rdata; s_rd <= 0;
  endtask

  logic [31:0] a, bb;
  initial begin
    repeat (3) @(posedge clock); reset = 0; @(posedge clock);

    bus_read(4'h4, a); bus_read(4'hc, bb);
    chk(a[0] === 1'b0 && bb[0] === 1'b0, "both flags start 0");

    // write CTRL_A: only FSM A wakes
    bus_write(4'h0, 32'h1);
    bus_read(4'h4, a); bus_read(4'hc, bb);
    chk(a[0]  === 1'b1, "CTRL_A write -> FSM A set STATUS_A.flag");
    chk(bb[0] === 1'b0, "CTRL_A write -> FSM B NOT woken (STATUS_B.flag still 0)");

    // write CTRL_B: only FSM B wakes
    bus_write(4'h8, 32'h1);
    bus_read(4'hc, bb);
    chk(bb[0] === 1'b1, "CTRL_B write -> FSM B set STATUS_B.flag");

    if (errors == 0) $display("[mmio_multi] PASS");
    else             $display("[mmio_multi] FAIL (%0d errors)", errors);
    $finish;
  end
  initial begin #20000; $display("[mmio_multi] TIMEOUT"); $finish; end
endmodule
"""


def _design():
    rep = ErrorReporter()
    files = [str(MMIO_MULTI / f) for f in ("mmio_multi_pkg.sv", "mmio_multi_tb.sv")]
    d = synth_mmio_design(files, FlowConfig(), rep, top_name="multi_top")
    assert d is not None and not rep.has_errors(), rep.report()
    # one regblock, two distinct FSM modules, one top
    assert {m for m, _sv in d.fsms} == {"multi_fsm_a", "multi_fsm_b"}
    return d


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_two_fsms_one_model_lints(tmp_path):
    d = _design()
    for fn, txt in d.files().items():
        (tmp_path / fn).write_text(txt)
    lint = subprocess.run(
        [str(VERILATOR), "--lint-only", "-Wall", "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL",
         "--top-module", "multi_top", *d.files().keys()],
        cwd=tmp_path, capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout + lint.stderr


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_two_fsms_one_model_simulates(tmp_path):
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
    assert "[mmio_multi] PASS" in run.stdout, run.stdout + run.stderr
