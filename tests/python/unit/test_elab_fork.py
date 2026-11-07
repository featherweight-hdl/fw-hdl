"""fork/join in timed code, from SV: translated to a Par, lowered into the
process, and cycle-exact against the class model in Verilator. join_none,
join_any and branches that race are rejected; so is fork in untimed code
(test_elab_untimed.py). See docs/methodology/timing.md (timed code)."""
import random

import pytest

from fw.hdl.fe.elab.translate import TranslateError
from zuspec.synth.proc import ir as P
from zuspec.synth.proc.lower import LowerError

from _elab_helpers import (RV1_SV, have_verilator, lower_sv, sim_class, sim_netlist,
                           translate_sv)

needs_verilator = pytest.mark.skipif(not have_verilator(), reason="needs verilator")


def design(branches, join="join"):
    """A timed component: get x (ready/valid), then fork the branches,
    which drive two no-handshake outputs a and b."""
    return RV1_SV + f'''
package fj_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    (* fw_timed *)
    class fj extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) src;
        fw_port #(fw_put_if #(bit [7:0])) ao;
        fw_port #(fw_put_if #(bit [7:0])) bo;
        bit [7:0] n;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            ao  = new("ao", this);
            bo  = new("bo", this);
        endfunction
        virtual task run();
            bit [7:0] x;
            forever begin
                src.t.get(x);
                fork
{branches}
                {join}
                n = n + 1;
            end
        endtask
    endclass
endpackage

module fj_top (input clock, input reset,
               input src_valid, output src_ready, input [7:0] src_data,
               output [7:0] a, output [7:0] b);
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import rv1_pkg::*;
    import fj_pkg::*;
    rv1_in_if #(bit [7:0]) u_src (.clock(clock), .reset(reset),
        .valid(src_valid), .ready(src_ready), .data(src_data));
    fw_put_xtor_if #(bit [7:0]) u_a (.clock(clock), .reset(reset), .out(a));
    fw_put_xtor_if #(bit [7:0]) u_b (.clock(clock), .reset(reset), .out(b));
    class fj_bind extends fw_component_root #(fj);
        function new(string name); super.new(name); endfunction
        virtual function void connect();
            rv1_get_x #(bit [7:0]) gs;
            fw_put_xtor_bridge #(bit [7:0]) ba, bb;
            gs = new("src_x", this, u_src);
            ba = new("a_x", this, u_a);
            bb = new("b_x", this, u_b);
            src.connect(gs);
            ao.connect(ba);
            bo.connect(bb);
            super.connect();
        endfunction
    endclass
    fw_root #(.Tbind(fj_bind)) u_root (.clock(clock), .reset(reset));
endmodule
'''


# a: two beats (2 cycles); b: two idle cycles, then one beat (3 cycles)
TWO = '''
                    begin
                        ao.t.put(x);
                        ao.t.put(x + 1);
                    end
                    begin
                        bo.t.put(8'h00);
                        bo.t.put(8'h00);
                        bo.t.put(~x);
                    end'''


def pars(st):
    out = []

    def walk(stmts):
        for s in stmts:
            if isinstance(s, P.Par):
                out.append(len(s.branches))
            for sub in ([s.then, s.orelse] if isinstance(s, P.If) else
                        [s.body] if isinstance(s, (P.Loop, P.Region)) else []):
                walk(sub)
    for p in st.design.procs:
        walk(p.body)
    return out


def test_fork_join_is_a_par(tmp_path):
    st = translate_sv(design(TWO), "fj_top", tmp_path)
    assert pars(st) == [2]


TB = '''
module fj_tb;
    reg clock = 0, reset = 1;
    reg src_valid = 0;
    reg [7:0] src_data = 0;
    wire src_ready;
    wire [7:0] a, b;
    int i = 0;
    int unsigned s = 7;
    bit [7:0] xs[6] = '{8'h10, 8'h22, 8'h3f, 8'h40, 8'h5a, 8'h61};
    fj_top u_dut (.*);
    always #5 clock = ~clock;
    function automatic bit coin();
        s = s * 1103515245 + 12345;
        return s[16] | s[17];
    endfunction
    always @(posedge clock) if (!reset && src_valid && src_ready) i <= i + 1;
    always @(negedge clock) begin
        src_valid <= !reset && i < 6 && coin();
        src_data  <= xs[i < 6 ? i : 0];
    end
    initial begin
        repeat (3) @(posedge clock);
        reset <= 0;
        repeat (60) begin
            @(posedge clock);
            #1 $display("O %0d %0d", a, b);
        end
        $display("X done");
        $finish;
    end
endmodule
'''


@pytest.mark.verilator
@needs_verilator
def test_fork_join_netlist_matches_class_cycle_for_cycle(tmp_path):
    text = design(TWO)
    low = lower_sv(text, "fj_top", tmp_path)
    a = [tuple(map(int, l.split()[1:])) for l in sim_class(text, "fj_top", TB, "fj_tb", tmp_path)
         if l.startswith("O ")]
    b = [tuple(map(int, l.split()[1:])) for l in sim_netlist(low, TB, "fj_tb", tmp_path)
         if l.startswith("O ")]
    xs = [0x10, 0x22, 0x3f, 0x40, 0x5a, 0x61]
    # per input x: a shows x then x+1 on consecutive cycles, while b shows
    # 0, 0, then ~x: the branches start together and the join waits for b
    for x in xs:
        k = next(i for i, (_va, vb) in enumerate(b) if vb == (~x) & 0xff) - 2
        assert b[k][0] == x and b[k + 1][0] == (x + 1) & 0xff
        assert b[k][1] == 0 and b[k + 1][1] == 0
    # and the class model agrees cycle for cycle (it starts one cycle later)
    assert a[1:] == b[:-1] or a == b


def test_join_none_is_rejected(tmp_path):
    with pytest.raises(TranslateError, match="join_none inside a process"):
        translate_sv(design(TWO, join="join_none"), "fj_top", tmp_path)


def test_join_any_is_not_supported_yet(tmp_path):
    with pytest.raises(TranslateError, match="join_any is not supported yet"):
        translate_sv(design(TWO, join="join_any"), "fj_top", tmp_path)


def test_branches_writing_the_same_field_are_rejected(tmp_path):
    racy = '''
                    begin ao.t.put(x); n = x; end
                    begin bo.t.put(x); bo.t.put(x); n = 8'h1; end'''
    with pytest.raises((TranslateError, LowerError), match="both write"):
        lower_sv(design(racy), "fj_top", tmp_path)


def test_branches_on_one_port_are_rejected(tmp_path):
    """Two branches driving the same transactor write the same interface
    signals: a race."""
    racy = '''
                    begin ao.t.put(x); end
                    begin bo.t.put(x); ao.t.put(x); end'''
    with pytest.raises(LowerError, match="fork branch"):
        lower_sv(design(racy), "fj_top", tmp_path)
