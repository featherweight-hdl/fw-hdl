"""Shared calls (translate ``share_calls``): case arms that each assign one
call of the same function to the same target call it once, the arguments
that differ selected by the arm.

The design has two cases on an input word:
  - a plain case on constants (disjoint items): arms 1, 3 and 4 call ``f``,
    arm 2 between them calls ``g``. All three share. Arm 4's argument calls
    ``bump()``, which counts in a member: it must count in that arm only.
  - a ``case (1'b1)`` on input bits, whose items overlap: arms 1 and 2
    (adjacent) call ``f`` and share, the first match still winning; arm 4
    calls ``f`` too, but arm 3 is between them and can match with it, so arm 4
    keeps its own call.

The netlist is checked against a Python model, with the option on and off."""
import random
import re

import pytest

from _elab_helpers import RV1_SV, _write, have_verilator, lower_sv, run_verilator, rv1_top, \
    translate_sv

needs_verilator = pytest.mark.skipif(not have_verilator(), reason="needs verilator")

PKG = RV1_SV + r'''
package sc_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    class sc extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [31:0])) src;
        fw_port #(fw_put_if #(bit [31:0])) dst;
        bit [7:0] n;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            dst = new("dst", this);
        endfunction
        function bit [7:0] f(input bit [7:0] a, input bit [7:0] b, input bit s);
            if (s) return a - b;
            return (a << b[2:0]) ^ b;
        endfunction
        function bit [7:0] g(input bit [7:0] a);
            return ~a;
        endfunction
        function bit [7:0] bump();
            n = n + 8'd1;
            return n;
        endfunction
        virtual task run();
            bit [31:0] x;
            bit [7:0] r, q;
            forever begin
                src.t.get(x);
                case (x[2:0])
                    3'd0:    r = f(x[15:8], x[23:16], x[24]);
                    3'd1:    r = g(x[15:8]);
                    3'd2:    r = f(x[23:16], 8'd3, 1'b0);
                    3'd3:    r = f(x[15:8], bump(), x[24]);
                    default: r = 8'hee;
                endcase
                case (1'b1)
                    x[5]:    q = f(x[15:8], 8'd1, 1'b1);
                    x[4]:    q = f(x[23:16], 8'd2, 1'b1);
                    x[3]:    q = g(x[23:16]);
                    x[6]:    q = f(x[15:8], x[23:16], 1'b0);
                    default: q = 8'h55;
                endcase
                dst.t.put({8'd0, n, q, r});
            end
        endtask
    endclass
endpackage
'''

TOP = rv1_top("sc_top", "sc", {"src": "bit [31:0]"}, {"dst": "bit [31:0]"}, ["sc_pkg"])


def f(a, b, s):
    return (a - b) & 0xff if s else ((a << (b & 7)) & 0xff) ^ b


def model(xs):
    n, out = 0, []
    for x in xs:
        lo, hi, s = (x >> 8) & 0xff, (x >> 16) & 0xff, (x >> 24) & 1
        k = x & 7
        if k == 0:
            r = f(lo, hi, s)
        elif k == 1:
            r = ~lo & 0xff
        elif k == 2:
            r = f(hi, 3, 0)
        elif k == 3:
            n = (n + 1) & 0xff
            r = f(lo, n, s)
        else:
            r = 0xee
        if x >> 5 & 1:
            q = f(lo, 1, 1)
        elif x >> 4 & 1:
            q = f(hi, 2, 1)
        elif x >> 3 & 1:
            q = ~hi & 0xff
        elif x >> 6 & 1:
            q = f(lo, hi, 0)
        else:
            q = 0x55
        out.append((n << 16) | (q << 8) | r)
    return out


_r = random.Random(11)
XS = [_r.randrange(1 << 32) for _ in range(150)]


def tb(xs):
    vals = ", ".join(f"32'd{x}" for x in xs)
    return f'''
module sc_tb;
    reg clock = 0, reset = 1;
    reg src_valid = 0, dst_ready = 1;
    reg [31:0] src_data = 0;
    wire src_ready, dst_valid;
    wire [31:0] dst_data;
    bit [31:0] xs[{len(xs)}] = '{{{vals}}};
    int i = 0, n = 0, cyc = 0;
    sc_top u (.*);
    always #5 clock = ~clock;
    always @(posedge clock) if (!reset) begin
        cyc <= cyc + 1;
        if (dst_valid && dst_ready) begin
            $display("O %0d", dst_data);
            n++;
        end
        if (src_valid && src_ready) i++;
    end
    always @(negedge clock) begin
        src_valid <= !reset && (i < {len(xs)});
        src_data  <= xs[i < {len(xs)} ? i : 0];
    end
    initial begin
        repeat (3) @(posedge clock);
        reset <= 0;
        while (n < {len(xs)} && cyc < 5000) @(posedge clock);
        $display("X done");
        $finish;
    end
endmodule
'''


def _stages(tmp_path, on):
    p = _write(PKG, tmp_path, "sc_pkg.sv")
    return translate_sv(TOP, "sc_top", tmp_path / "t", files=[p], keep_loops=True,
                        share_calls=on)


def _copies(st, fn):
    """The inlined copies of ``fn``: its return var, one per call site."""
    return {v.name for v in st.design.vars if re.search(rf"_run_{fn}_{fn}(_\d+)?$", v.name)}


def test_notes(tmp_path):
    notes = [n for n in _stages(tmp_path, True).notes if "share one call" in n]
    assert len(notes) == 2, notes
    assert any("case arms 1, 3, 4 share one call of f (3 of 3 arguments selected)" in n
               for n in notes), notes
    assert any("case arms 1, 2 share one call of f (2 of 3 arguments selected)" in n
               for n in notes), notes
    assert not [n for n in _stages(tmp_path / "off", False).notes if "share one call" in n]


def test_one_body_per_group(tmp_path):
    """Off: six copies of f; on: one per group, and the second case's arm 4."""
    assert len(_copies(_stages(tmp_path / "off", False), "f")) == 6
    assert len(_copies(_stages(tmp_path / "on", True), "f")) == 3
    assert len(_copies(_stages(tmp_path / "on2", True), "g")) == 2


@pytest.mark.verilator
@needs_verilator
@pytest.mark.parametrize("on", [False, True])
def test_netlist(tmp_path, on):
    p = _write(PKG, tmp_path, "sc_pkg.sv")
    low = lower_sv(TOP, "sc_top", tmp_path / "n", files=[p], share_calls=on)
    nf = _write(low.verilog, tmp_path, "netlist.v")
    out = run_verilator([nf, _write(tb(XS), tmp_path, "sc_tb.sv")], "sc_tb", tmp_path / "sim",
                        with_lib=False)
    assert [int(l.split()[1]) for l in out if l.startswith("O ")] == model(XS)
