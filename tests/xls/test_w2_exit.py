"""W2 exit (schedulable-library-plan.md): a parameterized structural top with
a loop of NVC credited links (credit sender -> valid-only channel -> receiver
returning credits, each link a nested structural component), an extern child
and a register-block child whose registers reach an XLS child as levels. It
partitions, integrates, and the class model and the RTL give the same stream
under the in-order contract once the register writes have landed.
"""
import random
from pathlib import Path

import pytest

from fw.hdl.verif.canon import Event, Rule, check, compare
from fw.hdl.xls_flow import sv_to_structure
from xls_harness import REPO, proc_testbench, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "compose"
FILES = [str(COMPOSE / f) for f in ("hier_pkg.sv", "kinds_pkg.sv", "mixed_pkg.sv",
                                     "regs_pkg.sv", "exit_pkg.sv")]
EXTERN = {"ext_neg": {"signature": str(COMPOSE / "ext_neg_rtl.sig.json"),
                      "module": "ext_neg_rtl", "files": [str(COMPOSE / "ext_neg_rtl.sv")]}}
RTL_LIB = [REPO / "src" / "rtl" / n for n in ("fw_rv_fifo.sv", "fw_valid_check.sv",
                                             "fw_xls_fifo_wrapper.sv")]
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")


XLS = ["vinc", "srx", "kadd"]
K, LO = 0x17, 0xc3
#: {addr, data} register writes: k, then p
CFG = [(0 << 32) | K, (4 << 32) | (0x1234 << 16) | LO]


def ref(x, nvc):
    for _ in range(nvc):
        x = ((x + 1) & 0xff) ^ 0x5a
    return ((((~x) & 0xff) + K) & 0xff) ^ LO


def trace(want, outs):
    ev = [Event("in", "in", i, i, data=w) for i, w in enumerate(want)]
    return ev + [Event("out", "out", len(want) + j, j, data=v) for j, v in enumerate(outs)]


@pytest.mark.parametrize("top, nvc", [("exit2_t", 2), ("exit3_t", 3)])
def test_exit_partition(top, nvc):
    from fw.hdl.spl_flow import partition
    sh = partition(FILES, top, XLS, extern=EXTERN).shell
    assert {c["name"]: c["engine"] for c in sh.children} == {
        **{f"lk_{i}": "structural" for i in range(nvc)},
        "e": "extern", "rc": "native", "ka": "xls"}
    link = sh.nested(sh.children[0])
    assert {c["name"]: c["kind"] for c in link.channels} == {"v": "valid", "cr": "ready_valid"}


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("stages", [1, 2])
@pytest.mark.parametrize("top, nvc", [("exit2_t", 2), ("exit3_t", 3)])
def test_exit_both_views(tmp_path, top, nvc, stages):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, top, XLS, extern=EXTERN, stages=stages)
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    xs = [r.randrange(256) for r in [random.Random(nvc)] for _ in range(200)]
    want = [ref(x, nvc) for x in xs]
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, {"cfg": CFG, "in": xs}, 8, after={"in": "cfg"}))
    out = run_verilator(paths + [COMPOSE / "ext_neg_rtl.sv"] + RTL_LIB + [tb], "xh_rtl_tb",
                        tmp_path / "rtl", with_lib=False, extra=["--assert", "+define+ASSERT_ON"])
    rtl = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    comp = sv_to_structure(FILES, top).component
    mtb = tmp_path / "xh_proc_tb.sv"
    mtb.write_text(proc_testbench(["exit_pkg"], top, comp, {"cfg": CFG, "in": xs},
                                  after={"in": "cfg"}))
    mout = run_verilator(FILES + [mtb], "xh_proc_tb", tmp_path / "model")
    model = [int(l.split()[3], 16) for l in mout if l.startswith("O out ")]
    assert check(trace(want, rtl), Rule()) == []
    assert compare(trace(want, model), trace(want, rtl), Rule(), names=("model", "rtl")) == []
