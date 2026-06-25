"""M8: equivalence of the *generated* regblock RTL against the live SV register
model. The same software write/read sequence is applied to both the emitted RTL
(bus side) and the `dma_channel_regs` fw_reg model, and the readback is compared
on every read — proving the M5->M6 lowering preserves behavior. A directed phase
then checks the hardware-update + read-to-clear paths against the model.
"""
import subprocess
from pathlib import Path

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.reg_mapper import build_reg_blocks
from fw.hdl.emit.regblock import emit_regblock

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "src"
VERILATOR = REPO / "packages" / "verilator" / "bin" / "verilator"


def _harness(block):
    """tb declarations + named connections for every regblock port (hwif tied
    off; the directed phase drives a couple explicitly)."""
    decls, conns = [], [".clock", ".reset", ".s_addr", ".s_wr", ".s_wdata",
                        ".s_rd", ".s_rdata"]
    for _off, qreg, reg in block.flat_registers():
        for f in reg.fields:
            if not f.sw_write and not f.hw_write:
                continue
            s = f"{qreg}__{f.name}"
            if f.hw_write:
                decls += [f"  logic [{f.width-1}:0] hwif_in_{s}_next = 0;",
                          f"  logic hwif_in_{s}_we = 0;"]
                conns += [f".hwif_in_{s}_next", f".hwif_in_{s}_we"]
            decls.append(f"  logic [{f.width-1}:0] hwif_out_{s};")
            conns.append(f".hwif_out_{s}")
    return "\n".join(decls), ",\n    ".join(conns)


_TB = """
module tb;
  import fw_hdl_pkg::*;
  import reg_dma_pkg::*;

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

  dma_channel_regs mdl;          // the reference model
  logic [31:0] exp, rtl_val;
  logic [4:0]  off;

  // Fully synchronous, posedge-only protocol. Stimulus is driven nonblocking so
  // it is stable for the next posedge; the write commit / read-accept happen on
  // the posedge. The readback is combinational, so it is captured into rtl_val
  // nonblocking AT the accept edge -- using the same pre-edge state the design's
  // read-clear uses, so capture and clear stay consistent (race-free).
  task automatic do_wr(input [4:0] a, input [31:0] data);
    @(posedge clock); s_addr <= a; s_wdata <= data; s_wr <= 1; s_rd <= 0;
    @(posedge clock); s_wr <= 0;            // write committed at this edge (s_wr=1)
    mdl.write_val(a, data);                 // mirror into the model
  endtask
  task automatic do_rd(input [4:0] a);
    @(posedge clock); s_addr <= a; s_rd <= 1; s_wr <= 0;
    @(posedge clock); s_rd <= 0; rtl_val <= s_rdata;   // accept edge: capture, RTL clears
    exp = mdl.read_val(a);                              // model returns pre-clear, clears
    @(posedge clock);                                  // rtl_val settled
    chk(rtl_val === exp, $sformatf("rd 0x%02h: rtl=0x%08h mdl=0x%08h", a, rtl_val, exp));
  endtask

  initial begin
    mdl = new("mdl");
    repeat (3) @(posedge clock); reset = 0; @(posedge clock);

    // ---- randomized software-write/read equivalence (decode, masks, mux) ----
    for (int n = 0; n < 400; n++) begin
      off = ($urandom % 8) << 2;            // word offsets 0x00..0x1c
      if ($urandom % 2) do_wr(off, $urandom);
      else              do_rd(off);
    end

    // ---- directed hardware-update + read-to-clear equivalence ---------------
    // hw sets busy (RO); model mirrors via the hardware update path
    @(posedge clock); hwif_in_csr__busy_next <= 1; hwif_in_csr__busy_we <= 1;
    @(posedge clock); hwif_in_csr__busy_we <= 0;     // update committed at this edge
    mdl.csr.update_val(32'h0000_0400, 32'h0000_0400);
    do_rd(5'h00); chk(rtl_val[10] === 1'b1, "busy set (equiv)");

    // hw sets int_done (ROC); first read sees it then both clear
    @(posedge clock); hwif_in_csr__int_done_next <= 1; hwif_in_csr__int_done_we <= 1;
    @(posedge clock); hwif_in_csr__int_done_we <= 0;
    mdl.csr.update_val(32'h0020_0000, 32'h0020_0000);
    do_rd(5'h00); chk(rtl_val[21] === 1'b1, "int_done set (equiv)");
    do_rd(5'h00); chk(rtl_val[21] === 1'b0, "int_done read-cleared (equiv)");

    if (errors == 0) $display("[regblock_equiv] PASS");
    else             $display("[regblock_equiv] FAIL (%0d errors)", errors);
    $finish;
  end
  initial begin #2000000; $display("[regblock_equiv] TIMEOUT"); $finish; end
endmodule
"""


@pytest.mark.skipif(not VERILATOR.exists(), reason="verilator not available")
def test_regblock_equivalent_to_model(reg_dma_files, tmp_path):
    rep = ErrorReporter()
    block = build_reg_blocks(reg_dma_files, FlowConfig(), rep)["dma_channel_regs"]
    assert not rep.has_errors(), rep.report()

    (tmp_path / "rb.sv").write_text(emit_regblock(block))
    decls, conns = _harness(block)
    (tmp_path / "tb.sv").write_text(
        _TB.format(decls=decls, conns=conns, mod=f"{block.name}_regblock"))

    build = subprocess.run(
        [str(VERILATOR), "--binary", "--timing", "-j", "0", "-Wno-fatal",
         f"+incdir+{SRC}", f"+incdir+{SRC / 'std'}",
         f"+incdir+{REPO / 'tests' / 'reg_dma'}",
         "--top-module", "tb", "-o", "simv",
         str(SRC / "fw_clock_xtor_if.sv"), str(SRC / "fw_hdl_pkg.sv"),
         str(REPO / "tests" / "reg_dma" / "reg_dma_pkg.sv"),
         "rb.sv", "tb.sv"],
        cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / "obj_dir" / "simv")],
                         cwd=tmp_path, capture_output=True, text=True)
    assert "[regblock_equiv] PASS" in run.stdout, run.stdout + run.stderr
