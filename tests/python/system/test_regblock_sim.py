"""M6: behavioral sim of the *generated* regblock RTL (self-contained — the
regblock module has no dependencies). Proves the emitted core matches the
register-model semantics on the DMA channel block: config RW, RO (sw write
ignored), hardware status update, and read-to-clear.

The DUT is generic; the directed stimulus below necessarily references specific
channel-block fields (that is the test's job), but the emitter under test never
keys off names.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.reg_mapper import build_reg_blocks
from fw.hdl.emit.regblock import emit_regblock

REPO = Path(__file__).resolve().parents[3]
VERILATOR = REPO / "packages" / "verilator" / "bin" / "verilator"


def _hwif_harness(block):
    """Generate tb declarations + named port connections for every regblock port,
    driven from the RegBlock field list (so the harness is layout-complete)."""
    decls, conns = [], [
        ".clock", ".reset", ".s_addr", ".s_wr", ".s_wdata", ".s_rd", ".s_rdata",
    ]
    for _off, qreg, reg in block.flat_registers():
        for f in reg.fields:
            if not f.sw_write and not f.hw_write:
                continue
            s = f"{qreg}__{f.name}"
            if f.hw_write:
                decls.append(f"  logic [{f.width-1}:0] hwif_in_{s}_next = 0;")
                decls.append(f"  logic hwif_in_{s}_we = 0;")
                conns.append(f".hwif_in_{s}_next")
                conns.append(f".hwif_in_{s}_we")
            decls.append(f"  logic [{f.width-1}:0] hwif_out_{s};")
            conns.append(f".hwif_out_{s}")
    return "\n".join(decls), ",\n    ".join(conns)


_TB = """
module tb;
  logic clock = 0, reset = 1;
  always #5 clock = ~clock;

  logic [4:0]  s_addr = 0;
  logic        s_wr = 0, s_rd = 0;
  logic [31:0] s_wdata = 0, s_rdata;
{decls}

  {mod} dut (
    {conns}
  );

  int errors = 0;
  task automatic chk(bit c, string m); if (!c) begin $display("FAIL: %s", m); errors++; end endtask

  task automatic wr(input [4:0] a, input [31:0] d);
    @(posedge clock); s_addr <= a; s_wdata <= d; s_wr <= 1;
    @(posedge clock); s_wr <= 0;
  endtask
  task automatic rd(input [4:0] a, output [31:0] d);
    s_addr = a; s_rd = 1; #1 d = s_rdata;     // combinational readback (pre-clear)
    @(posedge clock); s_rd <= 0;              // accepted read applies read-clear
  endtask

  localparam logic [4:0] CSR = 5'h00, AM0 = 5'h0c;
  logic [31:0] v;

  initial begin
    repeat (3) @(posedge clock); reset = 0; @(posedge clock);

    // config RW: ch_en (bit0) software-writable
    wr(CSR, 32'h0000_0001); rd(CSR, v); chk(v[0] === 1'b1, "ch_en RW");

    // RO: busy (bit10) is hw-only -> software write ignored
    wr(CSR, 32'h0000_0400); rd(CSR, v); chk(v[10] === 1'b0, "busy RO sw-write ignored");

    // hardware status update: drive busy via hwif
    @(posedge clock); hwif_in_csr__busy_next <= 1; hwif_in_csr__busy_we <= 1;
    @(posedge clock); hwif_in_csr__busy_we <= 0;
    rd(CSR, v); chk(v[10] === 1'b1, "busy set by hw");

    // read-to-clear: hw sets int_done (bit21); first read sees it, then it clears
    @(posedge clock); hwif_in_csr__int_done_next <= 1; hwif_in_csr__int_done_we <= 1;
    @(posedge clock); hwif_in_csr__int_done_we <= 0;
    rd(CSR, v); chk(v[21] === 1'b1, "int_done set (pre-clear read)");
    rd(CSR, v); chk(v[21] === 1'b0, "int_done read-cleared");

    // a different register decodes independently (am0 addr field, bits 31:2)
    wr(AM0, 32'hABCD_1230); rd(AM0, v); chk(v[31:2] === 30'h2AF3_448C, "am0 decode");
    rd(CSR, v); chk(v[10] === 1'b1, "csr undisturbed by am0 write");

    if (errors == 0) $display("[regblock_sim] PASS"); else $display("[regblock_sim] FAIL");
    $finish;
  end
  initial begin #10000; $display("[regblock_sim] TIMEOUT"); $finish; end
endmodule
"""


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_channel_regblock_behavior(reg_dma_files, tmp_path):
    rep = ErrorReporter()
    block = build_reg_blocks(reg_dma_files, FlowConfig(), rep)["dma_channel_regs"]
    assert not rep.has_errors(), rep.report()

    (tmp_path / "rb.sv").write_text(emit_regblock(block))
    decls, conns = _hwif_harness(block)
    (tmp_path / "tb.sv").write_text(
        _TB.format(decls=decls, conns=conns, mod=f"{block.name}_regblock"))

    build = subprocess.run(
        [str(VERILATOR), "--binary", "--timing", "-j", "0", "-Wno-fatal",
         "--top-module", "tb", "-o", "simv", "rb.sv", "tb.sv"],
        cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr

    simv = tmp_path / "obj_dir" / "simv"
    run = subprocess.run([str(simv)], cwd=tmp_path, capture_output=True, text=True)
    assert "[regblock_sim] PASS" in run.stdout, run.stdout + run.stderr
