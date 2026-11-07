"""Loops reach the process IR as loops (``keep_loops``): a static `for` loop
that doesn't wait is kept as ``P.Loop(trip=N)`` for an engine to unroll, fold
or pipeline; ``unroll_loops`` gives the as-written (unrolled) form back. When
the body needs the index as a constant, translate unrolls as before.

The designs: a 4-round toy block cipher (the shape of an AES round loop), a
triangular nest, and a scan with a `break`."""
import random

import pytest

from zuspec.synth.proc import ir as P

from _elab_helpers import (RV1_SV, have_verilator, lower_sv, rv1_top, sim_class, sim_netlist,
                           translate_sv)

needs_verilator = pytest.mark.skipif(not have_verilator(), reason="needs verilator")


def comp(name, body, decls="", w=32):
    """A get/put component over ready/valid: get x, run ``body``, put y."""
    return RV1_SV + f'''
package {name}_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    class {name} extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [{w - 1}:0])) src;
        fw_port #(fw_put_if #(bit [{w - 1}:0])) dst;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            dst = new("dst", this);
        endfunction
        virtual task run();
            bit [{w - 1}:0] x, y;
{decls}
            forever begin
                src.t.get(x);
{body}
                dst.t.put(y);
            end
        endtask
    endclass
endpackage
''' + rv1_top(f"{name}_top", name, {"src": f"bit [{w - 1}:0]"}, {"dst": f"bit [{w - 1}:0]"},
              imports=[f"{name}_pkg"])


ROUNDS = comp("rounds", '''
                y = x;
                for (int r = 0; r < 4; r++)
                    y = {y[23:0], y[31:24]} ^ (32'h9e3779b9 * (r + 1));''')


def rounds_ref(x):
    y = x
    for r in range(4):
        y = (((y << 8) | (y >> 24)) & 0xffffffff) ^ ((0x9e3779b9 * (r + 1)) & 0xffffffff)
    return y


TRI = comp("tri3", '''
                y = 0;
                for (int i = 0; i < 4; i++)
                    for (int j = 0; j < i; j++)
                        y = y + (x >> (8 * j));''')


def tri_ref(x):
    y = 0
    for i in range(4):
        for j in range(i):
            y = (y + (x >> (8 * j))) & 0xffffffff
    return y


# (8 iterations: lowering a longer chain of breaks grows exponentially, in
# both paths; impl-plan.md finding F4)
SCAN = comp("scan", '''
                y = 0;
                for (int i = 0; i < 8; i++) begin
                    if (x[i]) break;
                    y = y + 1;
                end''')


def scan_ref(x):
    n = 0
    while n < 8 and not (x >> n) & 1:
        n += 1
    return n


def trips(st):
    out = []

    def walk(stmts):
        for s in stmts:
            if isinstance(s, P.Loop):
                if s.trip is not None:
                    out.append(s.trip)
                walk(s.body)
            elif isinstance(s, P.If):
                walk(s.then)
                walk(s.orelse)
            elif isinstance(s, P.Region):
                walk(s.body)
    for p in st.design.procs:
        walk(p.body)
    return out


def test_round_loop_is_kept(tmp_path):
    st = translate_sv(ROUNDS, "rounds_top", tmp_path, keep_loops=True)
    assert trips(st) == [4]
    assert trips(translate_sv(ROUNDS, "rounds_top", tmp_path / "u")) == []


def test_index_dependent_inner_bound_falls_back(tmp_path):
    """The inner bound depends on i: the outer loop is unrolled, and each
    inner loop (now static) is kept."""
    st = translate_sv(TRI, "tri3_top", tmp_path, keep_loops=True)
    assert trips(st) == [0, 1, 2, 3]


def test_loop_with_break_is_kept(tmp_path):
    st = translate_sv(SCAN, "scan_top", tmp_path, keep_loops=True)
    assert trips(st) == [8]


def _tb(top, xs):
    vals = ", ".join(f"32'h{x:08x}" for x in xs)
    return f'''
module {top}_tb;
    reg clock = 0, reset = 1;
    reg src_valid = 0, dst_ready = 0;
    reg [31:0] src_data = 0;
    wire src_ready, dst_valid;
    wire [31:0] dst_data;
    bit [31:0] xs[{len(xs)}] = '{{{vals}}};
    int i = 0, n = 0, cyc = 0;
    int unsigned s = 11;
    {top} u_dut (.*);
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
        while (n < {len(xs)} && cyc < 4000) @(posedge clock);
        $display("X done");
        $finish;
    end
endmodule
'''


@pytest.mark.verilator
@needs_verilator
@pytest.mark.parametrize("name, text, ref", [
    ("rounds", ROUNDS, rounds_ref), ("tri3", TRI, tri_ref), ("scan", SCAN, scan_ref)])
def test_kept_loops_unrolled_match_the_class_model(tmp_path, name, text, ref):
    r = random.Random(name)
    xs = [r.randrange(1 << 32) for _ in range(24)] + [0, 1 << 31, 1]
    tb = _tb(f"{name}_top", xs)
    kept = lower_sv(text, f"{name}_top", tmp_path / "k", keep_loops=True)
    plain = lower_sv(text, f"{name}_top", tmp_path / "p", keep_loops=False)
    a = [l.split()[1:] for l in sim_class(text, f"{name}_top", tb, f"{name}_top_tb", tmp_path / "c")
         if l.startswith("O ")]
    b = [l.split()[1:] for l in sim_netlist(kept, tb, f"{name}_top_tb", tmp_path / "k")
         if l.startswith("O ")]
    c = [l.split()[1:] for l in sim_netlist(plain, tb, f"{name}_top_tb", tmp_path / "p")
         if l.startswith("O ")]
    assert [int(v) for _, v in b] == [ref(x) for x in xs]
    assert b == c                   # kept-then-unrolled == unrolled in translate
    assert a == b                   # and the class model, cycle for cycle
