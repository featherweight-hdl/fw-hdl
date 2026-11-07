"""The schedule as source (impl-plan.md E): the front end keeps each call to
another object as a call site and names the fields; the schedule is emitted
as a class that extends the source class (fe.elab.flow.emit_sched_pkg,
zuspec.synth.proc.emit_src). Read back in place of the source class, it
lowers to a netlist that behaves the same, and it simulates cycle for cycle
like the original class. See docs/methodology/timing.md (emitted source)."""
import pytest

from fw.hdl.fe.elab.flow import emit_sched_pkg
from zuspec.synth.proc import ir as P
from zuspec.synth.proc import sched

from _elab_helpers import (RV1_SV, _write, have_verilator, lower_sv, sim_class, sim_netlist,
                           translate_sv)

needs_verilator = pytest.mark.skipif(not have_verilator(), reason="needs verilator")

# A timed component with a fork (test_elab_fork.py's), and the top that binds
# it, or the emitted class with FJ_SCHED.
PKG = RV1_SV + '''
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
                    begin
                        ao.t.put(x);
                        ao.t.put(x + n);
                    end
                    begin
                        bo.t.put(8'h00);
                        bo.t.put(~x);
                    end
                join
                n = n + 1;
            end
        endtask
    endclass
endpackage
'''

TOP = '''
module fj_top (input clock, input reset,
               input src_valid, output src_ready, input [7:0] src_data,
               output [7:0] a, output [7:0] b);
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import rv1_pkg::*;
    import fj_pkg::*;
`ifdef FJ_SCHED
    import fj_top_sched_pkg::*;
    `define FJ_CLS fj_sched
`else
    `define FJ_CLS fj
`endif
    rv1_in_if #(bit [7:0]) u_src (.clock(clock), .reset(reset),
        .valid(src_valid), .ready(src_ready), .data(src_data));
    fw_put_xtor_if #(bit [7:0]) u_a (.clock(clock), .reset(reset), .out(a));
    fw_put_xtor_if #(bit [7:0]) u_b (.clock(clock), .reset(reset), .out(b));
    class fj_bind extends fw_component_root #(`FJ_CLS);
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


def sites(stmts, acc=None):
    acc = [] if acc is None else acc
    for s in stmts:
        if isinstance(s, P.Region):
            if s.site is not None:
                acc.append(s.site)
            else:
                sites(s.body, acc)
        for sub in ([s.then, s.orelse] if isinstance(s, P.If) else
                    [s.body] if isinstance(s, P.Loop) else
                    s.branches if isinstance(s, P.Par) else []):
            sites(sub, acc)
    return acc


def emitted(tmp_path):
    """The front end's stages for the source, and the emitted package."""
    pkg = _write(PKG, tmp_path, "fj_pkg.sv")
    st = translate_sv(TOP, "fj_top", tmp_path, files=[pkg], keep_loops=True)
    name, text = emit_sched_pkg(st.design, sched.schedule(st.design))
    return pkg, st, name, text


def outs(lines):
    return [tuple(map(int, l.split()[1:])) for l in lines if l.startswith("O ")]


def test_call_sites_fields_and_the_process_class(tmp_path):
    _pkg, st, _name, _text = emitted(tmp_path)
    run = next(p for p in st.design.procs if p.name == "root_run")
    assert (run.obj, run.task) == ("root", "fj.run")
    assert [(c.recv, c.method, c.dirs) for c in sites(run.body)] == [
        ("src.t", "get", ["out"]), ("ao.t", "put", ["in"]), ("ao.t", "put", ["in"]),
        ("bo.t", "put", ["in"]), ("bo.t", "put", ["in"])]
    n = next(v for v in st.design.vars if v.member == "n")
    assert (n.obj, n.flat) == ("root", True)
    src = st.design.class_src["root_run"]
    assert src.package == "fj_pkg" and src.ctor == [("string", "name"),
                                                    ("fw_component", "parent")]


def test_the_emitted_package(tmp_path):
    _pkg, _st, name, text = emitted(tmp_path)
    assert name == "fj_top_sched_pkg"
    assert "package fj_top_sched_pkg;" in text and "import fj_pkg::*;" in text
    assert "class fj_sched extends fj;" in text
    for line in ("src.t.get(", "fork", "ao.t.put(", "bo.t.put(8'h0);", "join",
                 "n = (n + 8'h1);"):
        assert line in text, line


def test_round_trip_lowers_the_same(tmp_path):
    """The emitted class, read back in place of fj, lowers to the same number
    of states and the same registers; the two netlists agree cycle for cycle."""
    pkg, _st, name, text = emitted(tmp_path)
    sp = _write(text, tmp_path, f"{name}.sv")
    a = lower_sv(TOP, "fj_top", tmp_path / "a", files=[pkg])
    b = lower_sv(TOP, "fj_top", tmp_path / "b", files=[pkg, sp], defines={"FJ_SCHED": "1"})
    states = lambda low: [l for l in low.report if l.startswith("root_run: ")]
    assert states(a) == states(b) and states(a)
    regs = lambda low: sorted((r.name, r.w) for r in low.netlist.regs
                              if not r.name.startswith("fj_bind_run"))
    assert regs(a) == regs(b)
    if have_verilator():
        sa = outs(sim_netlist(a, TB, "fj_tb", tmp_path / "a"))
        sb = outs(sim_netlist(b, TB, "fj_tb", tmp_path / "b"))
        assert sa == sb and any(x != (0, 0) for x in sa)


@pytest.mark.verilator
@needs_verilator
def test_the_emitted_class_runs_like_the_source(tmp_path):
    """The emitted class simulates exactly like the source class (and so,
    like the source, cycle for cycle like the netlist after its start-up)."""
    pkg, _st, name, text = emitted(tmp_path)
    sp = _write(text, tmp_path, f"{name}.sv")
    src = outs(sim_class(TOP, "fj_top", TB, "fj_tb", tmp_path / "src", files=[pkg]))
    emi = outs(sim_class(TOP, "fj_top", TB, "fj_tb", tmp_path / "emi", files=[pkg, sp],
                         defines={"FJ_SCHED": "1"}))
    assert emi == src and any(x != (0, 0) for x in src)
