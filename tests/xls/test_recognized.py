"""Recognized classes. A child whose class has a registry entry is
lowered by the entry (fw.hdl.lib), not mapped from its body:

* fw_arbiter #(.., FW_ARB_RR) lowers to the XLS IR template
  (fw.hdl.lib.xls_ir); fw_credit_tx, a cycle step, is mapped from its step();
* the class model and the RTL agree under each class's contract: in order for
  the credited link, in order per input for the arbiter;
* a parameter value the entry does not take is rejected at the child's line
  (tests/xls/lib/test_arbiter.py);
* a subclass that defines run() is rejected (its body would be replaced).
"""
import random
from pathlib import Path

import pytest

from fw.hdl.lib import xls_ir
from fw.hdl.verif.canon import Event, Rule, check, compare
from fw.hdl.xls_flow import sv_to_structure
from xls_harness import REPO, proc_testbench, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "compose"
FILES = [str(COMPOSE / "lib_pkg.sv")]
RTL_LIB = [REPO / "src" / "rtl" / n for n in ("fw_rv_fifo.sv", "fw_valid_check.sv")]
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")
XLS = {"ctop": ["crx", "fw_credit_tx"], "atop": []}


def _rtl(tmp_path, top, inputs, seed, stages=1):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, top, XLS[top], stages=stages)
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, inputs, seed))
    out = run_verilator(paths + RTL_LIB + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    return [int(l.split()[3], 16) for l in out if l.startswith("O out ")]


def _model(tmp_path, top, inputs):
    comp = sv_to_structure(FILES, top).component
    tb = tmp_path / "xh_proc_tb.sv"
    # The credit sender is a cycle step and the arbiter grants once a clock.
    tb.write_text(proc_testbench(["lib_pkg"], top, comp, inputs, clocked=True))
    out = run_verilator(FILES + [tb], "xh_proc_tb", tmp_path / "model")
    return [int(l.split()[3], 16) for l in out if l.startswith("O out ")]


def test_lowerings():
    from fw.hdl.spl_flow import partition
    a = partition(FILES, "atop", [])
    (arb,) = list(a.texts)
    assert a.texts[arb] == xls_ir.package(arb, xls_ir.rr_arb(
        n=3, width=8, name=arb, ins=["in_0", "in_1", "in_2"], out="out"))
    # recognized: no knob names it, and its body is not mapped
    assert [f.name for f in a.blocks[arb].fields] == ["in_0", "in_1", "in_2", "out"]
    # fw_credit_tx is a cycle step with no entry: its step() is mapped.
    c = partition(FILES, "ctop", XLS["ctop"])
    assert c.texts == {}
    assert {ch["name"]: ch.get("recognized") for ch in c.shell.children} == \
        {"tx": None, "rx": None}
    (tx,) = [k for k in c.blocks if k.startswith("fw_credit_tx")]
    assert c.blocks[tx].proc_processes[0].metadata == {"fw_step": True}
    assert [f.name for f in c.blocks[tx].fields][:3] == ["in_0", "cr", "out"]


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("stages", [1, 2])
def test_credit_tx_model_and_rtl_agree(tmp_path, stages):
    xs = [r.randrange(256) for r in [random.Random(stages)] for _ in range(150)]
    want = [x ^ 0x3c for x in xs]
    tr = lambda outs: [Event("in", "in", i, i, data=w) for i, w in enumerate(want)] + \
        [Event("out", "out", len(want) + j, j, data=v) for j, v in enumerate(outs)]  # noqa: E731
    rtl = _rtl(tmp_path, "ctop", {"in": xs}, seed=stages + 2, stages=stages)
    model = _model(tmp_path, "ctop", {"in": xs})
    assert check(tr(rtl), Rule()) == []
    assert compare(tr(model), tr(rtl), Rule(), names=("model", "rtl")) == []


def _arb_trace(ins, outs):
    """Keyed by input; an item is its value (all distinct). Out values are
    {index, value}."""
    ev = [Event("in", "in", n, x, key=k, data=(k << 8) | x)
          for n, (k, x) in enumerate((k, x) for k, xs in enumerate(ins) for x in xs)]
    return ev + [Event("out", "out", 10_000 + j, v & 0xff, key=v >> 8, data=v)
                 for j, v in enumerate(outs)]


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("stages", [1, 2])
def test_arbiter_model_and_rtl_agree_per_input(tmp_path, stages):
    vals = random.Random(7 + stages).sample(range(256), 120)
    ins = [vals[0:40], vals[40:80], vals[80:120]]
    inputs = dict(zip("abc", ins))
    rtl = _rtl(tmp_path, "atop", inputs, seed=stages, stages=stages)
    model = _model(tmp_path, "atop", inputs)
    rule = Rule(per_key=True)
    assert len(rtl) == len(model) == 120
    assert check(_arb_trace(ins, rtl), rule) == []
    assert compare(_arb_trace(ins, model), _arb_trace(ins, rtl), rule,
                   names=("model", "rtl")) == []


@needs_xls
@pytest.mark.verilator
def test_arbiter_round_robin_when_all_inputs_wait(tmp_path):
    """With every input full and out always ready, grants rotate 0, 1, 2, ...
    in both views."""
    ins = [[0x10 + i for i in range(6)], [0x20 + i for i in range(6)], [0x30 + i for i in range(6)]]
    model = _model(tmp_path, "atop", dict(zip("abc", ins)))
    assert [v >> 8 for v in model] == [0, 1, 2] * 6


def test_fixed_priority_lowers_to_the_prio_template():
    from fw.hdl.spl_flow import partition
    p = partition(FILES, "ptop", [])
    (arb,) = list(p.texts)
    assert p.texts[arb] == xls_ir.package(arb, xls_ir.rr_arb(
        n=3, width=8, name=arb, ins=["in_0", "in_1", "in_2"], out="out", prio=True))


SUB = """\
package sub_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    class my_arb extends fw_arbiter #(bit [7:0], 2);
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        virtual task run();
        endtask
    endclass
    class s_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) a;
        fw_port #(fw_get_if #(bit [7:0])) b;
        fw_port #(fw_put_if #(bit [8:0])) out;
        my_arb                            arb;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this);
            b = new("b", this);
            out = new("out", this);
            arb = new("arb", this);
        endfunction
        function void connect();
            arb.in[0].connect(a);
            arb.in[1].connect(b);
            arb.out.connect(out);
        endfunction
    endclass
endpackage
"""


def test_subclass_defining_run_is_rejected(tmp_path):
    from fw.hdl.errors import FwHdlError
    from fw.hdl.spl_flow import partition
    f = tmp_path / "sub_pkg.sv"
    f.write_text(SUB)
    with pytest.raises(FwHdlError) as e:
        partition([str(f)], "s_top", [])
    assert "my_arb extends fw_arbiter" in str(e.value) and "sub_pkg.sv:8:" in str(e.value), \
        str(e.value)


def test_registry_lists_fw_hdl_entries():
    from fw.hdl.lib.registry import ORIGIN, registry
    got = {(e.name, e.target) for e in registry().externals() if e.origin == ORIGIN}
    assert {x for x in got if x[1] != "elab"} == \
        {("fw_arbiter", "xls"), ("fw_reg_component", "native")}
    # the channel classes and port APIs the front end matches are entries too
    assert {n for n, t in got if t == "elab"} == {
        "fw_channel", "fw_valid_channel", "fw_level_channel", "fw_get_if", "fw_get_nb_if",
        "fw_put_if", "fw_valid_put_if", "fw_level_if", "fw_level_set_if"}
