"""fw_resource: hazard-lock operations from SV, after PDL. A memcpy-style
component reads through one port and writes through another; a resource
`mem` orders the two (the state behind the ports, which the compiler can't
see). The class model runs the resource's sequential checks; the lowering
reads the calls as ``Lock`` statements, checks them on every path, and erases
them: the netlist is the one without the resource."""
import random

import pytest

from zuspec.synth.proc import ir as P
from zuspec.synth.proc.lower import LowerError

from _elab_helpers import (RV1_SV, VerilatorError, have_verilator, lower_sv, rv1_top, sim_class,
                           sim_netlist, translate_sv)
from test_elab_loops import _tb

needs_verilator = pytest.mark.skipif(not have_verilator(), reason="needs verilator")

GOOD = '''
                mem.acquire(a, FW_READ);
                src.t.get(x);
                mem.free(a);
                mem.acquire(a + 8'd16, FW_WRITE);
                dst.t.put(x + 1);
                mem.free(a + 8'd16);'''

PLAIN = '''
                src.t.get(x);
                dst.t.put(x + 1);'''


def design(body, guard=True):
    g = '(* fw_guard="mem" *) ' if guard else ""
    return RV1_SV + f'''
package cpy_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    // copies a stream from src (at a) to dst (at a + 16): two ports, one
    // memory behind them
    class cpy extends fw_component implements fw_runnable;
        {g}fw_port #(fw_get_if #(bit [31:0])) src;
        {g}fw_port #(fw_put_if #(bit [31:0])) dst;
        fw_resource #(bit [7:0]) mem;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            dst = new("dst", this);
            mem = new("mem");
        endfunction
        virtual task run();
            bit [31:0] x;
            bit [7:0] a = 0;
            forever begin
{body}
                a++;
            end
        endtask
    endclass
endpackage
''' + rv1_top("cpy_top", "cpy", {"src": "bit [31:0]"}, {"dst": "bit [31:0]"},
              imports=["cpy_pkg"])


def locks(st):
    out = []

    def walk(stmts):
        for s in stmts:
            if isinstance(s, P.Lock):
                out.append((s.op, s.rw))
            elif isinstance(s, P.If):
                walk(s.then)
                walk(s.orelse)
            elif isinstance(s, (P.Loop, P.Region)):
                walk(s.body)
    for p in st.design.procs:
        walk(p.body)
    return out


def test_calls_become_lock_statements(tmp_path):
    st = translate_sv(design(GOOD), "cpy_top", tmp_path)
    assert locks(st) == [("reserve", "r"), ("block", ""), ("access", ""), ("release", ""),
                         ("reserve", "w"), ("block", ""), ("access", ""), ("release", "")]


def test_locks_are_erased(tmp_path):
    a = lower_sv(design(GOOD), "cpy_top", tmp_path / "a")
    b = lower_sv(design(PLAIN, guard=False), "cpy_top", tmp_path / "b")
    assert a.verilog == b.verilog


def test_access_after_release_is_an_error(tmp_path):
    bad = GOOD.replace("""                mem.free(a + 8'd16);""", "").replace(
        """                dst.t.put(x + 1);""",
        """                mem.free(a + 8'd16);
                dst.t.put(x + 1);""")
    with pytest.raises(LowerError, match=r"accesses root\.mem outside an acquire"):
        lower_sv(design(bad), "cpy_top", tmp_path)


MISUSE = GOOD.replace("mem.acquire(a + 8'd16, FW_WRITE);", "mem.reserve(a + 8'd16, FW_WRITE);")


def test_misuse_is_an_error_at_lowering(tmp_path):
    # the put, between the reserve and the free, is the first misuse on the path
    with pytest.raises(LowerError, match=r"cpy_top.sv:\d+: root_run: accesses root\.mem outside"):
        lower_sv(design(MISUSE), "cpy_top", tmp_path)


@pytest.mark.verilator
@needs_verilator
def test_misuse_is_reported_by_the_class_model(tmp_path):
    with pytest.raises(VerilatorError, match="before block"):
        sim_class(design(MISUSE), "cpy_top", _tb("cpy_top", [1, 2, 3]), "cpy_top_tb", tmp_path)


@pytest.mark.verilator
@needs_verilator
def test_class_model_matches_the_netlist(tmp_path):
    r = random.Random("cpy")
    xs = [r.randrange(1 << 31) for _ in range(20)]
    tb = _tb("cpy_top", xs)
    low = lower_sv(design(GOOD), "cpy_top", tmp_path / "n")
    a = [l.split()[1:] for l in sim_class(design(GOOD), "cpy_top", tb, "cpy_top_tb", tmp_path)
         if l.startswith("O ")]
    b = [l.split()[1:] for l in sim_netlist(low, tb, "cpy_top_tb", tmp_path / "n")
         if l.startswith("O ")]
    assert [int(v) for _, v in b] == [x + 1 for x in xs]
    assert a == b


def test_guard_must_name_a_resource(tmp_path):
    text = design(GOOD).replace('(* fw_guard="mem" *) fw_port #(fw_get_if',
                                '(* fw_guard="dst" *) fw_port #(fw_get_if')
    with pytest.raises(Exception, match=r'src is \(\* fw_guard="dst" \*\), but dst is not an '
                                        'fw_resource'):
        translate_sv(text, "cpy_top", tmp_path)


def test_other_methods_are_not_for_processes(tmp_path):
    text = design(GOOD.replace("src.t.get(x);", "src.t.get(x);\n if (mem.held(a)) x = 0;"))
    with pytest.raises(Exception, match=r"root\.mem\.held\(\) is not supported in a process"):
        translate_sv(text, "cpy_top", tmp_path)
