"""RQ-F1: structural components are elaborated (fe/elab/hier.py), so build()
and connect() may loop, branch on parameters, use arrays and configure children
with parameter objects. Each case is checked as structure, then as RTL (one
XLS block per distinct child, integrated) against a reference.
"""
import json
import random
from pathlib import Path

import pytest

from fw.hdl.xls_flow import sv_to_structure
from xls_harness import REPO, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
FILES = [str(HERE / "compose" / "hier_pkg.sv")]
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")


def roles(st):
    return {f.name: f.pragmas.get("fw_role", "port") for f in st.component.fields}


def binds(st):
    from fw.hdl.spl_flow import _path_name
    c = st.component
    return sorted((_path_name(c, b.lhs), _path_name(c, b.rhs)) for b in c.bind_map)


def test_loop_n_structure():
    st = sv_to_structure(FILES, "loop4_t")
    r = roles(st)
    assert [n for n, k in r.items() if k == "child"] == [f"stage_{i}" for i in range(4)]
    assert [n for n, k in r.items() if k == "channel"] == ["ch_0", "ch_1", "ch_2"]
    assert (("stage_0", "in"), ("in", None)) in binds(st)
    assert (("stage_1", "in"), ("ch_0", "get_ex")) in binds(st)
    assert (("stage_3", "out"), ("out", None)) in binds(st)
    # four instances of one specialization: one block
    assert len({c.spelling for c in st.children.values()}) == 1
    assert next(iter(st.children.values())).spelling.startswith("add_k__")


@pytest.mark.parametrize("top, kids", [("cond1_t", ["a", "b"]), ("cond0_t", ["a"])])
def test_cond_child_structure(top, kids):
    st = sv_to_structure(FILES, top)
    assert [n for n, k in roles(st).items() if k == "child"] == kids
    assert ("c" in roles(st)) == (len(kids) == 2)


def test_param_obj_is_two_blocks():
    st = sv_to_structure(FILES, "param_top")
    s0, s1 = st.children["s0"], st.children["s1"]
    assert s0.param_values == {"mul": 3, "add": 1} and s1.param_values == {"mul": 2, "add": 5}
    assert s0.spelling != s1.spelling and s0.spelling.startswith("scale__")
    assert s0.alias == s1.alias == "scale"


def test_partition_is_deterministic(tmp_path):
    from fw.hdl.spl_flow import partition
    a = partition(FILES, "param_top", ["scale"]).shell.to_json()
    b = partition(FILES, "param_top", ["scale"]).shell.to_json()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert {c["alias"] for c in a["children"]} == {"scale"}


CASES = {
    "loop4_t": (["add_k"], lambda x: (x + 4) & 0xff),
    "cond1_t": (["add_k"], lambda x: (x + 3) & 0xff),
    "cond0_t": (["add_k"], lambda x: (x + 1) & 0xff),
    "param_top": (["scale"], lambda x: (((x * 3 + 1) & 0xff) * 2 + 5) & 0xff),
}


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("top", list(CASES))
def test_rtl_view_matches_reference(tmp_path, top):
    from fw.hdl.spl_flow import spl_to_rtl
    xls, ref = CASES[top]
    xs = [r.randrange(256) for r in [random.Random(7)] for _ in range(1)] + \
        [r.randrange(256) for r in [random.Random(top)] for _ in range(100)]
    design = spl_to_rtl(FILES, top, xls, stages=1)
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, {"in": xs}, 5))
    out = run_verilator(paths + [REPO / "src" / "rtl" / "fw_rv_fifo.sv", tb], "xh_rtl_tb",
                        tmp_path / "rtl", with_lib=False, extra=["--assert", "+define+ASSERT_ON"])
    got = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    assert got == [ref(x) for x in xs]
