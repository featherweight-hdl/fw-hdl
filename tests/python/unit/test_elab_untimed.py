"""Untimed code (the default for class code) and timed code
(docs/methodology/timing.md): untimed code writes no edges, and calls timed
code only through a latency-insensitive API; each such call is a timed region
tagged with the API method (one event to a scheduler). A timed class keeps the
cycle-exact reading: a UART transmitter's bit timing."""
import pytest

from zuspec.synth.proc import ir as P

from _elab_helpers import (RV1_SV, have_verilator, lower_sv, rv1_top, sim_class, sim_netlist,
                           translate_sv)
from fw.hdl.fe.elab.translate import TranslateError

needs_verilator = pytest.mark.skipif(not have_verilator(), reason="needs verilator")


def comp(run, extra="", mark=""):
    """A component with a get port and a put port on ready/valid bindings
    (latency-insensitive), a ``run()`` body and ``extra`` members."""
    return RV1_SV + f'''
package un_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    {mark}
    class un extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) src;
        fw_port #(fw_put_if #(bit [7:0])) dst;
        bit [7:0] n;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            dst = new("dst", this);
        endfunction
{extra}
        virtual task run();
{run}
        endtask
    endclass
endpackage
''' + rv1_top("un_top", "un", {"src": "bit [7:0]"}, {"dst": "bit [7:0]"}, imports=["un_pkg"])


def calls(st):
    """The timed calls made from untimed code in the run process."""
    out = []

    def walk(stmts):
        for s in stmts:
            if isinstance(s, P.Region):
                if s.call:
                    out.append(s.call)
                walk(s.body)
            elif isinstance(s, P.Loop):
                walk(s.body)
            elif isinstance(s, P.If):
                walk(s.then)
                walk(s.orelse)
    walk(next(p for p in st.design.procs if p.name == "root_run").body)
    return out


# -- what untimed code may not do ---------------------------------------------

@pytest.mark.parametrize("stmt, what", [
    ("wait (n == 3);", r"wait\(\) in untimed code \(un\.run\)"),
    ("#1;", r"a clock edge or delay in untimed code \(un\.run\)"),
])
def test_edges_in_untimed_code_are_errors(tmp_path, stmt, what):
    text = comp(f"            forever begin src.t.get(n); {stmt} dst.t.put(n); end")
    with pytest.raises(TranslateError, match=what):
        translate_sv(text, "un_top", tmp_path)


def test_edges_in_untimed_helper_name_the_helper(tmp_path):
    extra = "        task settle(); wait (n != 0); endtask"
    text = comp("            forever begin src.t.get(n); settle(); dst.t.put(n); end", extra)
    with pytest.raises(TranslateError, match=r"untimed code \(un\.settle\)"):
        translate_sv(text, "un_top", tmp_path)


def test_timed_call_through_an_undeclared_binding_is_an_error(tmp_path):
    """fw_put_if over fw_put_xtor_if has no handshake: the output is sampled
    every cycle, so its timing matters."""
    text = f'''
module nd_top (input clock, input reset, output [7:0] out);
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    fw_put_xtor_if #(bit [7:0]) u_out (.clock(clock), .reset(reset), .out(out));
    class nd extends fw_component implements fw_runnable;
        fw_port #(fw_put_if #(bit [7:0])) dst;
        bit [7:0] n;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build(); dst = new("dst", this); endfunction
        virtual task run(); forever begin dst.t.put(n); n = n + 1; end endtask
    endclass
    class nd_bind extends fw_component_root #(nd);
        function new(string name); super.new(name); endfunction
        virtual function void connect();
            fw_put_xtor_bridge #(bit [7:0]) br;
            br = new("dst_x", this, u_out);
            dst.connect(br);
            super.connect();
        endfunction
    endclass
    fw_root #(.Tbind(nd_bind)) u_root (.clock(clock), .reset(reset));
endmodule
'''
    with pytest.raises(TranslateError,
                       match=r"untimed code \(nd\.run\) calls timed fw_put_xtor_bridge\.put "
                             r"\(called through fw_put_if\), which is not declared "
                             r"latency-insensitive"):
        translate_sv(text, "nd_top", tmp_path)
    # the same design, marked timed, is fine
    st = translate_sv(text.replace("    class nd extends", "    (* fw_timed *)\n    class nd extends"),
                      "nd_top", tmp_path)
    assert calls(st) == []


def test_timed_task_of_own_class_needs_a_declaration(tmp_path):
    extra = '''
        (* fw_timed *)
        task pace(); tick(2); endtask'''
    text = comp("            forever begin src.t.get(n); pace(); dst.t.put(n); end", extra)
    with pytest.raises(TranslateError, match=r"calls timed un\.pace"):
        translate_sv(text, "un_top", tmp_path)
    st = translate_sv(text.replace("(* fw_timed *)", "(* fw_timed, fw_latency_insensitive *)"),
                      "un_top", tmp_path)
    assert calls(st) == ["fw_get_if.get", "un.pace", "fw_put_if.put"]


# -- what it may ----------------------------------------------------------------

def test_declared_calls_are_tagged_timed_regions(tmp_path):
    st = translate_sv(comp("            forever begin src.t.get(n); dst.t.put(n + 1); end"),
                      "un_top", tmp_path)
    assert calls(st) == ["fw_get_if.get", "fw_put_if.put"]
    assert "call fw_get_if.get" in P.dump(st.design)


def test_tick_in_untimed_code_is_one_timed_call(tmp_path):
    st = translate_sv(comp("            forever begin src.t.get(n); tick(3); dst.t.put(n); end"),
                      "un_top", tmp_path)
    assert calls(st) == ["fw_get_if.get", "fw_component.tick", "fw_put_if.put"]


def test_functions_take_the_callers_context(tmp_path):
    extra = "        function bit [7:0] f(bit [7:0] x); return x ^ 8'h5a; endfunction"
    st = translate_sv(comp("            forever begin src.t.get(n); dst.t.put(f(n)); end", extra),
                      "un_top", tmp_path)
    assert calls(st) == ["fw_get_if.get", "fw_put_if.put"]


def test_rle_decoder_follows_the_rules(tmp_path):
    """A non-processor design from the XLS examples, untimed, on ready/valid."""
    from pathlib import Path
    x = Path(__file__).resolve().parents[3] / "examples" / "xls" / "rle"
    text = RV1_SV + rv1_top("rle_top", "rle_pkg::RunLengthDecoder32",
                            {"input_r": "rle_pkg::RunLengthDecoder32::DecInData"},
                            {"output_s": "rle_pkg::RunLengthDecoder32::DecOutData"})
    low = lower_sv(text, "rle_top", tmp_path, files=[x / "rle_pkg.sv"])
    assert calls(low.stages) == ["fw_get_if.get", "fw_put_if.put"]
    assert any(l.startswith("root_run: ") for l in low.report)


# -- a timed design: a UART transmitter ---------------------------------------

BIT = 4          # cycles per bit

UART = RV1_SV + f'''
package ut_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // Timed: the bit timing on the line is the point of this class.
    (* fw_timed *)
    class uart_tx extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) src;      // bytes (ready/valid)
        fw_port #(fw_put_if #(bit))       txd;      // the line (no handshake)
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            txd = new("txd", this);
        endfunction
        task send_bit(bit b);
            txd.t.put(b);
            tick({BIT - 1});
        endtask
        virtual task run();
            bit [7:0] b;
            // (a process blocks first inside its forever loop, so the line
            // goes high there: the stop bit, then idle until the next byte)
            forever begin
                send_bit(1'b1);                     // stop / idle
                src.t.get(b);
                send_bit(1'b0);                     // start
                for (int i = 0; i < 8; i++)
                    send_bit(b[i]);
            end
        endtask
    endclass
endpackage

module ut_top (input clock, input reset,
               input src_valid, output src_ready, input [7:0] src_data,
               output line);
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import rv1_pkg::*;
    import ut_pkg::*;
    rv1_in_if #(bit [7:0]) u_src (.clock(clock), .reset(reset),
        .valid(src_valid), .ready(src_ready), .data(src_data));
    fw_put_xtor_if #(bit) u_txd (.clock(clock), .reset(reset), .out(line));
    class ut_bind extends fw_component_root #(uart_tx);
        function new(string name); super.new(name); endfunction
        virtual function void connect();
            rv1_get_x #(bit [7:0]) gs;
            fw_put_xtor_bridge #(bit) bt;
            gs = new("src_x", this, u_src);
            bt = new("txd_x", this, u_txd);
            src.connect(gs);
            txd.connect(bt);
            super.connect();
        endfunction
    endclass
    fw_root #(.Tbind(ut_bind)) u_root (.clock(clock), .reset(reset));
endmodule
'''

BYTES = [0x55, 0xA3, 0x00, 0xFF, 0x3C]

UART_TB = f'''
module ut_tb;
    reg clock = 0, reset = 1;
    reg src_valid = 0;
    reg [7:0] src_data = 0;
    wire src_ready, line;
    bit [7:0] xs[{len(BYTES)}] = '{{{", ".join(f"8'h{b:02x}" for b in BYTES)}}};
    int i = 0;
    ut_top u_dut (.*);
    always #5 clock = ~clock;
    always @(posedge clock) if (!reset && src_valid && src_ready) i <= i + 1;
    always @(negedge clock) begin
        src_valid <= !reset && i < {len(BYTES)};
        src_data  <= xs[i < {len(BYTES)} ? i : 0];
    end
    initial begin
        repeat (3) @(posedge clock);
        reset <= 0;
        repeat ({(len(BYTES) + 1) * 10 * BIT + 20}) begin
            @(posedge clock);
            #1 $display("O %0d", line);
        end
        $display("X done");
        $finish;
    end
endmodule
'''


def decode(line):
    """Bytes from a sampled line: a start bit is a 1 -> 0 edge; sample each bit
    in the middle of its BIT cycles."""
    out, i = [], 1
    while i < len(line) - 10 * BIT:
        if line[i - 1] == 1 and line[i] == 0:
            bits = [line[i + BIT * (k + 1) + BIT // 2] for k in range(8)]
            out.append(sum(b << k for k, b in enumerate(bits)))
            i += 10 * BIT
        else:
            i += 1
    return out


def test_uart_lowers(tmp_path):
    low = lower_sv(UART, "ut_top", tmp_path)
    assert calls(low.stages) == []          # timed throughout
    assert any(l.startswith("root_run: ") for l in low.report)


@pytest.mark.verilator
@needs_verilator
def test_uart_netlist_matches_class_cycle_for_cycle(tmp_path):
    low = lower_sv(UART, "ut_top", tmp_path)
    a = [int(l.split()[1]) for l in sim_class(UART, "ut_top", UART_TB, "ut_tb", tmp_path)
         if l.startswith("O ")]
    b = [int(l.split()[1]) for l in sim_netlist(low, UART_TB, "ut_tb", tmp_path)
         if l.startswith("O ")]
    assert decode(b) == BYTES
    assert decode(a) == BYTES
    assert a[1:] == b[:-1]          # the class model starts one cycle later (fw_root)


def test_fork_in_untimed_code_is_an_error(tmp_path):
    text = comp("            forever begin src.t.get(n); fork n = n + 1; join dst.t.put(n); end")
    with pytest.raises(TranslateError, match=r"fork in untimed code \(un\.run\)"):
        translate_sv(text, "un_top", tmp_path)
