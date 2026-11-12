"""The elaborate-then-lower test harness (_elab_helpers.py), on two small
designs: a counter on a put port (no handshake) and a stream filter between
two ready/valid ports. Each is lowered, then the class model and the netlist
run on one testbench and are compared.

Startup: the class model starts one cycle after the netlist. fw_root builds the
component tree in the first cycle after reset is released, and run() starts
then; the netlist leaves reset in its run state. After that the two agree
cycle for cycle.
"""
import random
from pathlib import Path

import pytest

from _elab_helpers import (RV1_SV, have_verilator, lower_sv, rv1_top, sim_class, sim_netlist,
                           translate_sv)

needs_verilator = pytest.mark.skipif(not have_verilator(), reason="needs verilator")

# -- a counter: put(n) every cycle -------------------------------------------

CNT = r'''
module cnt_top (input clock, input reset, output [7:0] out);
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    fw_put_xtor_if #(bit [7:0]) u_out (.clock(clock), .reset(reset), .out(out));

    // Timed: one value per cycle on an output with no handshake.
    (* fw_timed *)
    class cnt extends fw_component implements fw_runnable;
        fw_port #(fw_put_if #(bit [7:0])) dst;
        bit [7:0] n;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            dst = new("dst", this);
        endfunction
        virtual task run();
            n = 0;
            forever begin
                dst.t.put(n);
                n = n + 3;
            end
        endtask
    endclass

    class cnt_bind extends fw_component_root #(cnt);
        function new(string name); super.new(name); endfunction
        virtual function void connect();
            fw_put_xtor_bridge #(bit [7:0]) br;
            br = new("dst_x", this, u_out);
            dst.connect(br);
            super.connect();
        endfunction
    endclass

    fw_root #(.Tbind(cnt_bind)) u_root (.clock(clock), .reset(reset));
endmodule
'''

CNT_TB = r'''
module cnt_tb;
    reg clock = 0, reset = 1;
    wire [7:0] out;
    cnt_top u_dut (.clock(clock), .reset(reset), .out(out));
    always #5 clock = ~clock;
    initial begin
        repeat (3) @(posedge clock);
        reset <= 0;
        repeat (20) begin
            @(posedge clock);
            #1 $display("O %0d", out);
        end
        $display("X done");
        $finish;
    end
endmodule
'''


def _outs(lines):
    return [l.split(None, 1)[1] for l in lines if l.startswith("O ")]


def test_counter_translates(tmp_path):
    st = translate_sv(CNT, "cnt_top", tmp_path)
    assert [p.name for p in st.design.procs if p.name.endswith("run")] == ["root_run"]


def test_counter_lowers(tmp_path):
    low = lower_sv(CNT, "cnt_top", tmp_path)
    assert "root_run: 1 states" in low.report
    assert "module cnt_top" in low.verilog


@pytest.mark.verilator
@needs_verilator
def test_counter_class_matches_netlist(tmp_path):
    low = lower_sv(CNT, "cnt_top", tmp_path)
    a = _outs(sim_class(CNT, "cnt_top", CNT_TB, "cnt_tb", tmp_path))
    b = _outs(sim_netlist(low, CNT_TB, "cnt_tb", tmp_path))
    assert b[:4] == ["0", "3", "6", "9"]
    assert a[1:] == b[:-1]          # the class model starts one cycle later


# -- a stream filter: get x, put 2x+1, over ready/valid ----------------------

FLT = RV1_SV + r'''
package flt_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class flt extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) src;
        fw_port #(fw_put_if #(bit [7:0])) dst;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            dst = new("dst", this);
        endfunction
        virtual task run();
            bit [7:0] x;
            forever begin
                src.t.get(x);
                dst.t.put(2 * x + 1);
            end
        endtask
    endclass
endpackage
''' + rv1_top("flt_top", "flt", {"src": "bit [7:0]"}, {"dst": "bit [7:0]"}, imports=["flt_pkg"])


def _flt_tb(xs, seed):
    """Random valid on the input and random ready on the output; prints each
    accepted output beat with its cycle."""
    vals = ", ".join(f"8'd{x}" for x in xs)
    return f'''
module flt_tb;
    reg clock = 0, reset = 1;
    reg src_valid = 0, dst_ready = 0;
    reg [7:0] src_data = 0;
    wire src_ready, dst_valid;
    wire [7:0] dst_data;
    bit [7:0] xs[{len(xs)}] = '{{{vals}}};
    int i = 0, n = 0, cyc = 0;
    int unsigned s = {seed};
    flt_top u_dut (.*);
    always #5 clock = ~clock;
    function automatic bit coin();
        s = s * 1103515245 + 12345;
        return s[16];
    endfunction
    always @(posedge clock) if (!reset) begin
        cyc <= cyc + 1;
        if (dst_valid && dst_ready) begin
            $display("O %0d %0d", cyc, dst_data);
            n++;
        end
        if (src_valid && src_ready) i++;
    end
    always @(negedge clock) begin
        src_valid <= !reset && (i < {len(xs)}) && coin();
        src_data  <= xs[i < {len(xs)} ? i : 0];
        dst_ready <= !reset && coin();
    end
    initial begin
        repeat (3) @(posedge clock);
        reset <= 0;
        while (n < {len(xs)} && cyc < 2000) @(posedge clock);
        $display("X done");
        $finish;
    end
endmodule
'''


def test_filter_lowers(tmp_path):
    low = lower_sv(FLT, "flt_top", tmp_path)
    assert any(l.startswith("root_run: ") for l in low.report)


@pytest.mark.verilator
@needs_verilator
def test_filter_class_matches_netlist(tmp_path):
    xs = [random.Random(3).randrange(128) for _ in range(1)] + \
        [r.randrange(128) for r in [random.Random(5)] for _ in range(40)]
    tb = _flt_tb(xs, 7)
    low = lower_sv(FLT, "flt_top", tmp_path)
    a = [l.split()[1:] for l in sim_class(FLT, "flt_top", tb, "flt_tb", tmp_path) if l.startswith("O ")]
    b = [l.split()[1:] for l in sim_netlist(low, tb, "flt_tb", tmp_path)
         if l.startswith("O ")]
    want = [str((2 * x + 1) & 0xff) for x in xs]
    assert [v for _, v in b] == want                 # port by port, in order
    assert a == b                                    # and cycle by cycle


# -- the lowering is the same in every run ------------------------------------

def test_lowering_is_seed_independent(tmp_path):
    """The netlist text doesn't depend on PYTHONHASHSEED (term hashes order
    commutative operands)."""
    import os
    import subprocess
    import sys
    here = Path(__file__).resolve().parent
    code = ("import sys; sys.path[:0] = [{h!r}, {t!r}, {p!r}];"
            "from pathlib import Path;"
            "import test_elab_harness as t, _elab_helpers as h;"
            "print(h.lower_sv(t.FLT, 'flt_top', Path(sys.argv[1])).verilog)").format(
                h=str(here), t=str(here.parents[1]), p=str(here.parents[2] / "python"))
    outs = set()
    for seed in ("1", "2"):
        r = subprocess.run([sys.executable, "-c", code, str(tmp_path / seed)],
                           env=dict(os.environ, PYTHONHASHSEED=seed),
                           capture_output=True, text=True, check=True)
        outs.add(r.stdout)
    assert len(outs) == 1
