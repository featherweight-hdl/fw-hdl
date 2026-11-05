"""An RTL-level component built directly as Zuspec IR (not lowered from a
class) renders to Verilog through fw.hdl.emit.be_sv: combinational outputs
from a comb process, a register updated by a sync process with reset. This is
the route an RTL-level library generator takes.

The block is a two-input round-robin arbiter: grant = valid, preferring the
input not granted last; `last` moves on a grant.
"""
from pathlib import Path

import pytest
import zuspec.ir.core as ir
from zuspec.synth.spl import builders as b

from fw.hdl.emit.be_sv import emit_sv
from xls_harness import VERILATOR, have_verilator, run_verilator

FIELDS = ["clk", "rst", "v0", "v1", "g0", "g1", "last"]


def arb2() -> ir.DataTypeComponent:
    i = {n: k for k, n in enumerate(FIELDS)}
    r = {n: b.sref(k) for n, k in i.items()}
    And, Or = ir.BinOp.BitAnd, ir.BinOp.BitOr
    comb = b.comb_proc("grant", [
        b.assign(r["g0"], b.binop(And, r["v0"], b.binop(Or, b.inv(r["v1"]), r["last"]))),
        b.assign(r["g1"], b.binop(And, r["v1"], b.binop(Or, b.inv(r["v0"]), b.inv(r["last"])))),
    ])
    sync = b.sync_proc("track", [
        b.if_(r["rst"], [b.assign(r["last"], b.const(0))],
              [b.if_(b.binop(Or, r["g0"], r["g1"]), [b.assign(r["last"], r["g1"])])]),
    ], clock_index=i["clk"], reset_index=i["rst"])
    fields = [b.in_port("clk"), b.in_port("rst"), b.in_port("v0"), b.in_port("v1"),
              b.out_reg("g0"), b.out_reg("g1"), b.reg("last")]
    return b.component("arb2", fields, sync_processes=[sync], comb_processes=[comb])


TB = """
module tb;
    logic clk = 0, rst = 1, v0 = 0, v1 = 0;
    wire g0, g1;
    arb2 dut(.clk(clk), .rst(rst), .v0(v0), .v1(v1), .g0(g0), .g1(g1));
    always #5 clk = ~clk;
    initial begin
        @(negedge clk); rst = 0;
        v0 = 1; v1 = 1;
        repeat (4) begin @(negedge clk); $display("g %0d%0d", g0, g1); end
        v1 = 0; @(negedge clk); $display("g %0d%0d", g0, g1);
        v0 = 0; v1 = 1; @(negedge clk); $display("g %0d%0d", g0, g1);
        $display("X done");
        $finish;
    end
endmodule
"""


@pytest.fixture(scope="module")
def text(tmp_path_factory):
    return emit_sv(ir.Context(type_m={"arb2": arb2()}),
                   out_dir=str(tmp_path_factory.mktemp("arb2")))


def test_emits_one_module(text):
    assert text.count("module arb2") == 1
    assert "always" in text


@pytest.mark.verilator
@pytest.mark.skipif(not have_verilator(), reason="needs verilator")
def test_lint_clean(text, tmp_path):
    import subprocess
    f = tmp_path / "arb2.sv"
    f.write_text(text)
    r = subprocess.run([str(VERILATOR), "--lint-only", "-Wall", str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.verilator
@pytest.mark.skipif(not have_verilator(), reason="needs verilator")
def test_alternates(text, tmp_path):
    (tmp_path / "arb2.sv").write_text(text)
    (tmp_path / "tb.sv").write_text(TB)
    out = [l for l in run_verilator([tmp_path / "arb2.sv", tmp_path / "tb.sv"], "tb",
                                    tmp_path, with_lib=False) if l.startswith("g ")]
    # both valid: alternate, starting at 0 after reset; then each alone
    assert out == ["g 10", "g 01", "g 10", "g 01", "g 10", "g 01"]
