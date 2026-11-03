"""The registry's ``zuspec`` target: an entry whose lowering is a factory that
builds the block as Zuspec IR from the class parameters.

The class here, zs_add #(K), adds K to each value; its step() is the model.
The entry's factory builds the same block by hand with the ir-core builders.
Partition takes the factory's component for the child (no knob names it),
and the component lowers through XLS like a mapped class: its RTL equals the
class model cycle for cycle.
"""
from pathlib import Path

import pytest

import zuspec.ir.core as ir
from fw.hdl.lib import registry as librg
from zuspec.be.xls.lower_proc import lower_component
from zuspec.be.xls.printer import format_package
from zuspec.be.xls.testing.xlstools import CodegenOptions, codegen_main, opt_main, run_codegen
from xls_harness import _trace, check_step, have_verilator, rtl_step_testbench, run_verilator

SV = '''`include "fw_std_macros.svh"
package zs_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // The class model: each value plus K. The registry builds its block.
    class zs_add #(int K = 1) extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(bit [7:0]))    in;
        fw_port #(fw_valid_put_if #(bit [7:0])) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual function void step();
            bit [7:0] x;
            if (in.t.try_get(x))
                out.t.put(x + 8'(K));
        endfunction
    endclass
    typedef zs_add #(5) zs_add5;

    class zs_top extends fw_component;
        fw_port #(fw_get_nb_if #(bit [7:0]))    a;
        fw_port #(fw_valid_put_if #(bit [7:0])) out;
        zs_add #(5) add;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this);
            out = new("out", this);
            add = new("add", this);
        endfunction
        function void connect();
            add.in.connect(a);
            add.out.connect(out);
        endfunction
    endclass
endpackage
'''

SCHED = {"in": [(0, 1), (1, 2), (1, 0xfe), (4, 7), (9, 9), (10, 0x80)]}
CYCLES = 16


def _add_block(params, name, ports):
    """zs_add as Zuspec IR: each cycle, poll `in`; if a value came, put it
    plus K on `out`."""
    u8, u1 = ir.DataTypeInt(bits=8, signed=False), ir.DataTypeInt(bits=1, signed=False)
    port = lambda i: ir.ExprRefField(base=ir.TypeExprRefSelf(), index=i)
    x, ok = ir.ExprRefLocal(name="x"), ir.ExprRefLocal(name="ok")
    poll = ir.ExprAwait(value=ir.ExprCall(func=ir.ExprAttribute(value=port(0), attr="try_get"),
                                          args=[x]))
    plus = ir.ExprBin(lhs=x, op=ir.BinOp.Add,
                      rhs=ir.ExprCast(target_type=u8, value=ir.ExprConstant(value=params["K"])))
    put = ir.ExprAwait(value=ir.ExprCall(func=ir.ExprAttribute(value=port(1), attr="put"),
                                         args=[plus]))
    body = [ir.StmtAnnAssign(target=x, annotation=ir.ExprConstant(value="bit [7:0]"),
                             ir_type=u8, value=None),
            ir.StmtAnnAssign(target=ok, annotation=ir.ExprConstant(value="bit"),
                             ir_type=u1, value=None),
            ir.StmtAssign(targets=[ok], value=poll),
            ir.StmtIf(test=ok, body=[ir.StmtExpr(expr=put)], orelse=[])]
    run = ir.Function(name="run", is_async=True, metadata={"fw_step": True},
                      body=[ir.StmtWhile(test=ir.ExprConstant(value=True), body=body)])
    comp = ir.DataTypeComponent(name=name, super=None, fields=[ports["in"], ports["out"]],
                                functions=[])
    comp.proc_processes = [run]
    return comp


@pytest.fixture
def entry():
    reg = librg.registry()
    reg.register_external("zs_add", {"K": range(0, 256)}, "zuspec",
                          librg.ZuspecLowering(_add_block), origin="test")
    yield
    reg._external.pop(("zs_add", "zuspec"), None)


def test_partition_takes_the_factorys_component(tmp_path, entry):
    from fw.hdl.spl_flow import partition
    f = tmp_path / "zs_pkg.sv"
    f.write_text(SV)
    part = partition([str(f)], "zs_top", [])
    (k,) = list(part.blocks)
    assert part.texts == {}
    blk = part.blocks[k]
    assert [f.name for f in blk.fields] == ["in", "out"]
    assert blk.proc_processes[0].body[0].body[2].targets[0].name == "ok"   # the factory's
    assert {ch["name"]: ch.get("recognized") for ch in part.shell.children} == \
        {"add": "zs_add"}


def test_parameter_outside_the_entry_rejected(tmp_path):
    from fw.hdl.errors import FwHdlError
    from fw.hdl.spl_flow import partition
    reg = librg.registry()
    reg.register_external("zs_add", {"K": range(0, 4)}, "zuspec",
                          librg.ZuspecLowering(_add_block), origin="test")
    try:
        f = tmp_path / "zs_pkg.sv"
        f.write_text(SV)
        with pytest.raises(FwHdlError, match=r"zs_pkg.sv:\d+:\d+: .*child 'add'"):
            partition([str(f)], "zs_top", [])
    finally:
        reg._external.pop(("zs_add", "zuspec"), None)


@pytest.mark.skipif(not have_verilator() or codegen_main() is None or opt_main() is None,
                    reason="needs Verilator, opt_main and codegen_main")
def test_factory_block_equals_the_model(tmp_path, entry):
    from fw.hdl.spl_flow import partition
    f = tmp_path / "zs_pkg.sv"
    f.write_text(SV)
    model = check_step([str(f)], "zs_pkg", "zs_add5", SCHED, CYCLES, tmp_path / "model")
    assert model["out"] == [(c, (v + 5) & 0xFF) for c, v in
                            [(0, 1), (1, 2), (2, 0xfe), (4, 7), (9, 9), (10, 0x80)]]
    (blk,) = partition([str(f)], "zs_top", []).blocks.values()
    res = run_codegen(format_package(lower_component(blk)), CodegenOptions(), stages=1)
    d = tmp_path / "factory"
    d.mkdir()
    (d / "b.sv").write_text(res.verilog)
    (d / "tb.sv").write_text(rtl_step_testbench(res.signature, SCHED, CYCLES))
    got = _trace(run_verilator([d / "b.sv", d / "tb.sv"], "xh_rtl_step_tb", d / "rtl",
                               with_lib=False))
    assert got["out"] == model["out"]
