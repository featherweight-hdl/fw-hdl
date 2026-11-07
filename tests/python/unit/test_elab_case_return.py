"""A `case` whose items return (impl-plan.md T2). picorv32's legal() and
lane_mask() were first written this way and lowered wrong: legal() gave 0 for
LUI and lane_mask() gave 0 for its default item.

The cause was in translate's run-time `if` (_dyn_if). An item whose value is
written out on one side (``r = off[1] ? ...``) and a constant on the other
(``return 4'hf``): merging the two writes the constant into the other side,
and the definite-assignment step then saw the var as written on one side only
and appended a default ``r = 0`` after it.

Each form below runs in a stream component; the netlist's output is checked
against a Python model."""
import random

import pytest

from zuspec.synth.proc import ir as P

from _elab_helpers import RV1_SV, _write, have_verilator, lower_sv, run_verilator, translate_sv

needs_verilator = pytest.mark.skipif(not have_verilator(), reason="needs verilator")

# picorv32's functions as first written: a case of returns
RETURNS = r'''
    function bit legal(input bit [31:0] i);
        bit [2:0] f3 = i[14:12];
        bit [6:0] f7 = i[31:25];
        case (i[6:0])
            7'b0110111, 7'b0010111, 7'b1101111: return 1'b1;
            7'b1100111: return f3 == 3'b000;
            7'b1100011: return f3 != 3'b010 && f3 != 3'b011;
            7'b0000011: return f3 != 3'b011 && f3 < 3'b110;
            7'b0100011: return f3 < 3'b011;
            7'b0010011: begin
                if (f3 == 3'b001) return f7 == 7'h00;
                if (f3 == 3'b101) return f7 == 7'h00 || f7 == 7'h20;
                return 1'b1;
            end
            7'b0110011: begin
                if (f3 == 3'b000 || f3 == 3'b101) return f7 == 7'h00 || f7 == 7'h20;
                return f7 == 7'h00;
            end
            7'b0001111: return f3 == 3'b000;
            default: return 1'b0;
        endcase
    endfunction
    function bit [3:0] lane_mask(input bit [1:0] sz, input bit [1:0] off);
        case (sz)
            2'b00:   return 4'b0001 << off;
            2'b01:   return off[1] ? 4'b1100 : 4'b0011;
            default: return 4'b1111;
        endcase
    endfunction
'''

# the same, with a result var per item and one return at the end
RESULT = r'''
    function bit legal(input bit [31:0] i);
        bit [2:0] f3 = i[14:12];
        bit [6:0] f7 = i[31:25];
        bit r;
        case (i[6:0])
            7'b0110111, 7'b0010111, 7'b1101111: r = 1'b1;
            7'b1100111: r = f3 == 3'b000;
            7'b1100011: r = f3 != 3'b010 && f3 != 3'b011;
            7'b0000011: r = f3 != 3'b011 && f3 < 3'b110;
            7'b0100011: r = f3 < 3'b011;
            7'b0010011: begin
                if (f3 == 3'b001) r = f7 == 7'h00;
                else if (f3 == 3'b101) r = f7 == 7'h00 || f7 == 7'h20;
                else r = 1'b1;
            end
            7'b0110011: begin
                if (f3 == 3'b000 || f3 == 3'b101) r = f7 == 7'h00 || f7 == 7'h20;
                else r = f7 == 7'h00;
            end
            7'b0001111: r = f3 == 3'b000;
            default: r = 1'b0;
        endcase
        return r;
    endfunction
    function bit [3:0] lane_mask(input bit [1:0] sz, input bit [1:0] off);
        bit [3:0] r;
        case (sz)
            2'b00:   r = 4'b0001 << off;
            2'b01:   r = off[1] ? 4'b1100 : 4'b0011;
            default: r = 4'b1111;
        endcase
        return r;
    endfunction
'''

FORMS = {"returns": RETURNS, "result": RESULT}


def pkg(funcs):
    return RV1_SV + '''
package cr_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    class cr extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [31:0])) src;
        fw_port #(fw_put_if #(bit [31:0])) dst;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            dst = new("dst", this);
        endfunction
''' + funcs + '''
        virtual task run();
            bit [31:0] x;
            forever begin
                src.t.get(x);
                dst.t.put({27'd0, legal(x), lane_mask(x[13:12], x[1:0])});
            end
        endtask
    endclass
endpackage
'''


TOP = '''
module cr_top (input clock, input reset,
               input src_valid, output src_ready, input [31:0] src_data,
               output dst_valid, input dst_ready, output [31:0] dst_data);
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import rv1_pkg::*;
    import cr_pkg::*;
    rv1_in_if #(bit [31:0]) u_src (.clock(clock), .reset(reset),
        .valid(src_valid), .ready(src_ready), .data(src_data));
    rv1_out_if #(bit [31:0]) u_dst (.clock(clock), .reset(reset),
        .valid(dst_valid), .ready(dst_ready), .data(dst_data));
    class cr_bind extends fw_component_root #(cr);
        function new(string name); super.new(name); endfunction
        virtual function void connect();
            rv1_get_x #(bit [31:0]) gs;
            rv1_put_x #(bit [31:0]) pd;
            gs = new("src_x", this, u_src);
            pd = new("dst_x", this, u_dst);
            src.connect(gs);
            dst.connect(pd);
            super.connect();
        endfunction
    endclass
    fw_root #(.Tbind(cr_bind)) u_root (.clock(clock), .reset(reset));
endmodule
'''


def legal(i):
    op, f3, f7 = i & 0x7f, (i >> 12) & 7, (i >> 25) & 0x7f
    if op in (0b0110111, 0b0010111, 0b1101111):
        return 1
    if op == 0b1100111:
        return int(f3 == 0)
    if op == 0b1100011:
        return int(f3 not in (2, 3))
    if op == 0b0000011:
        return int(f3 != 3 and f3 < 6)
    if op == 0b0100011:
        return int(f3 < 3)
    if op == 0b0010011:
        return int(f7 == 0) if f3 == 1 else int(f7 in (0, 0x20)) if f3 == 5 else 1
    if op == 0b0110011:
        return int(f7 in (0, 0x20)) if f3 in (0, 5) else int(f7 == 0)
    if op == 0b0001111:
        return int(f3 == 0)
    return 0


def lane_mask(sz, off):
    return [(1 << off) & 0xf, 0b1100 if off & 2 else 0b0011, 0xf, 0xf][sz]


def model(xs):
    return [(legal(x) << 4) | lane_mask((x >> 12) & 3, x & 3) for x in xs]


OPS = [0b0110111, 0b0010111, 0b1101111, 0b1100111, 0b1100011, 0b0000011, 0b0100011,
       0b0010011, 0b0110011, 0b0001111, 0b1110011]
_r = random.Random(5)
XS = [(_r.choice([0, 0x20, _r.randrange(128)]) << 25) | (_r.randrange(8) << 12)
      | (_r.randrange(32) << 7) | _r.choice(OPS) for _ in range(80)]


def tb(xs):
    vals = ", ".join(f"32'd{x}" for x in xs)
    return f'''
module cr_tb;
    reg clock = 0, reset = 1;
    reg src_valid = 0, dst_ready = 1;
    reg [31:0] src_data = 0;
    wire src_ready, dst_valid;
    wire [31:0] dst_data;
    bit [31:0] xs[{len(xs)}] = '{{{vals}}};
    int i = 0, n = 0, cyc = 0;
    cr_top u (.*);
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
        while (n < {len(xs)} && cyc < 3000) @(posedge clock);
        $display("X done");
        $finish;
    end
endmodule
'''


def _overwrites(stmts):
    """(var, values) for each var a statement list writes more than once, the
    last time with 0: a default after the value the branch carries out."""
    out, seen = [], {}
    for s in stmts:
        if isinstance(s, P.Assign):
            seen.setdefault(s.var.name, []).append(str(s.value))
        for ss in ([s.then, s.orelse] if isinstance(s, P.If) else
                   [s.body] if isinstance(s, (P.Loop, P.Region)) else []):
            out += _overwrites(ss)
    return out + [(v, vals) for v, vals in seen.items()
                  if len(vals) > 1 and vals[-1].endswith("'h0")]


@pytest.mark.parametrize("form", FORMS)
def test_no_default_after_a_merged_write(tmp_path, form):
    """No branch writes the result and then overwrites it with 0."""
    p = _write(pkg(FORMS[form]), tmp_path, "cr_pkg.sv")
    st = translate_sv(TOP, "cr_top", tmp_path / "t", files=[p], keep_loops=True)
    run = next(pr for pr in st.design.procs if pr.name == "root_run")
    assert [w for w in _overwrites(run.body) if "lane_mask" in w[0] or "legal" in w[0]] == []


@pytest.mark.verilator
@needs_verilator
@pytest.mark.parametrize("form", FORMS)
def test_netlist(tmp_path, form):
    p = _write(pkg(FORMS[form]), tmp_path, "cr_pkg.sv")
    low = lower_sv(TOP, "cr_top", tmp_path / "n", files=[p])
    nf = _write(low.verilog, tmp_path, "netlist.v")
    out = run_verilator([nf, _write(tb(XS), tmp_path, "cr_tb.sv")], "cr_tb", tmp_path / "sim",
                        with_lib=False)
    assert [int(l.split()[1]) for l in out if l.startswith("O ")] == model(XS)
