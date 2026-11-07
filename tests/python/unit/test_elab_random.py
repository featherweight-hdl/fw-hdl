"""The random engine (zuspec.synth.proc.sched.random, impl-plan.md step 5) on a
stream filter written as untimed class code. For each seed:

  - the netlist of the random schedule produces, port by port and in order,
    what the source's sequential reading says (a Python model here);
  - the schedule emitted as a class and read back (E.3) lowers to a netlist
    that agrees with it pin for pin, every cycle.

See docs/methodology/timing.md (Untimed code; Emitted source) and testing.md."""
import random
import re

import pytest

from fw.hdl.fe.elab.flow import emit_sched_pkg
from zuspec.synth.proc import ir as P
from zuspec.synth.proc import sched
from zuspec.synth.proc.emit import emit_verilog
from zuspec.synth.proc.lower import lower, optimize

from _elab_helpers import RV1_SV, _write, have_verilator, lower_sv, run_verilator, translate_sv

needs_verilator = pytest.mark.skipif(not have_verilator(), reason="needs verilator")

SEEDS = range(1, 21)

PKG = RV1_SV + '''
package rf_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class rf extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) src;
        fw_port #(fw_put_if #(bit [7:0])) dst;
        bit [7:0] acc;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            dst = new("dst", this);
        endfunction
        virtual task run();
            bit [7:0] x, y;
            forever begin
                src.t.get(x);
                acc = acc + x;
                if (x[0]) y = acc ^ x;
                else y = acc + 8'd3;
                for (int i = 0; i < 3; i++)
                    y = y + (x >> i);
                dst.t.put(y);
                if (x[1]) dst.t.put(acc);
            end
        endtask
    endclass
endpackage
'''

TOP = '''
module rf_top (input clock, input reset,
               input src_valid, output src_ready, input [7:0] src_data,
               output dst_valid, input dst_ready, output [7:0] dst_data);
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import rv1_pkg::*;
    import rf_pkg::*;
`ifdef RF_SCHED
    import rf_top_sched_pkg::*;
    `define RF_CLS rf_sched
`else
    `define RF_CLS rf
`endif
    rv1_in_if #(bit [7:0]) u_src (.clock(clock), .reset(reset),
        .valid(src_valid), .ready(src_ready), .data(src_data));
    rv1_out_if #(bit [7:0]) u_dst (.clock(clock), .reset(reset),
        .valid(dst_valid), .ready(dst_ready), .data(dst_data));
    class rf_bind extends fw_component_root #(`RF_CLS);
        function new(string name); super.new(name); endfunction
        virtual function void connect();
            rv1_get_x #(bit [7:0]) gs;
            rv1_put_x #(bit [7:0]) pd;
            gs = new("src_x", this, u_src);
            pd = new("dst_x", this, u_dst);
            src.connect(gs);
            dst.connect(pd);
            super.connect();
        endfunction
    endclass
    fw_root #(.Tbind(rf_bind)) u_root (.clock(clock), .reset(reset));
endmodule
'''

XS = [random.Random(11).randrange(256) for _ in range(1)] + \
    [r.randrange(256) for r in [random.Random(13)] for _ in range(30)]


def model(xs):
    """The source read as a sequential program: the output stream."""
    acc, out = 0, []
    for x in xs:
        acc = (acc + x) & 0xff
        y = acc ^ x if x & 1 else (acc + 3) & 0xff
        for i in range(3):
            y = (y + (x >> i)) & 0xff
        out.append(y)
        if x & 2:
            out.append(acc)
    return out


def tb(xs, seed=7):
    """Two netlists, rf_top_a and rf_top_b, on the same random valid/ready:
    every output compared every cycle (M on a difference), and each accepted
    output beat of a (O)."""
    vals = ", ".join(f"8'd{x}" for x in xs)
    n = len(model(xs))
    return f'''
module rf_tb;
    reg clock = 0, reset = 1;
    reg src_valid = 0, dst_ready = 0;
    reg [7:0] src_data = 0;
    wire a_src_ready, a_dst_valid, b_src_ready, b_dst_valid;
    wire [7:0] a_dst_data, b_dst_data;
    bit [7:0] xs[{len(xs)}] = '{{{vals}}};
    int i = 0, n = 0, cyc = 0;
    int unsigned s = {seed};
    rf_top_a u_a (.clock, .reset, .src_valid, .src_data, .dst_ready,
                  .src_ready(a_src_ready), .dst_valid(a_dst_valid), .dst_data(a_dst_data));
    rf_top_b u_b (.clock, .reset, .src_valid, .src_data, .dst_ready,
                  .src_ready(b_src_ready), .dst_valid(b_dst_valid), .dst_data(b_dst_data));
    always #5 clock = ~clock;
    function automatic bit coin();
        s = s * 1103515245 + 12345;
        return s[16];
    endfunction
    always @(posedge clock) if (!reset) begin
        cyc <= cyc + 1;
        if ({{a_src_ready, a_dst_valid, a_dst_data}} !== {{b_src_ready, b_dst_valid, b_dst_data}})
            $display("M %0d", cyc);
        if (a_dst_valid && dst_ready) begin
            $display("O %0d", a_dst_data);
            n++;
        end
        if (src_valid && a_src_ready) i++;
    end
    always @(negedge clock) begin
        src_valid <= !reset && (i < {len(xs)}) && coin();
        src_data  <= xs[i < {len(xs)} ? i : 0];
        dst_ready <= !reset && coin();
    end
    initial begin
        repeat (3) @(posedge clock);
        reset <= 0;
        while (n < {n} && cyc < 3000) @(posedge clock);
        $display("C %0d", cyc);
        $display("X done");
        $finish;
    end
endmodule
'''


def _rename(verilog, name):
    return re.sub(r"\bmodule\s+rf_top\b", f"module {name}", verilog, count=1)


@pytest.fixture(scope="module")
def front(tmp_path_factory):
    wd = tmp_path_factory.mktemp("rf")
    pkg = _write(PKG, wd, "rf_pkg.sv")
    return pkg, translate_sv(TOP, "rf_top", wd, files=[pkg], keep_loops=True)


def test_the_process_is_untimed_and_has_points(front):
    from zuspec.synth.proc.sched.random import edge_points
    _pkg, st = front
    run = next(p for p in st.design.procs if p.name == "root_run")
    assert run.timed is False
    assert all(p.timed for p in st.design.procs if p is not run and not p.comb)
    assert len(edge_points(st.design)) >= 5
    # the seeds below do move code: most add edges
    added = [seed for seed in SEEDS if f"random{seed}_" in
             P.dump(sched.schedule(st.design, f"random:seed={seed},n=4"))]
    assert len(added) >= 15


@pytest.mark.verilator
@needs_verilator
@pytest.mark.parametrize("seed", SEEDS)
def test_seed(tmp_path, front, seed):
    pkg, st = front
    s = sched.schedule(st.design, f"random:seed={seed},n=4")
    assert s.scheduled == f"random:{seed}"
    a = emit_verilog(optimize(lower(s)))
    name, text = emit_sched_pkg(st.design, s)
    assert f"random:{seed} schedule" in text
    sp = _write(text, tmp_path, f"{name}.sv")
    b = lower_sv(TOP, "rf_top", tmp_path / "b", files=[pkg, sp], defines={"RF_SCHED": "1"})
    fa = _write(_rename(a, "rf_top_a"), tmp_path, "a.v")
    fb = _write(_rename(b.verilog, "rf_top_b"), tmp_path, "b.v")
    tbf = _write(tb(XS), tmp_path, "rf_tb.sv")
    out = run_verilator([fa, fb, tbf], "rf_tb", tmp_path / "sim", with_lib=False)
    assert any(l.startswith("X done") for l in out)
    assert [l for l in out if l.startswith("M ")] == []                 # E.3: cycle for cycle
    assert [int(l.split()[1]) for l in out if l.startswith("O ")] == model(XS)   # port by port
