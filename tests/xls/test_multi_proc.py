"""Multi-proc islands. Children named in ``island.groups`` become one
XLS package (a proc per class, in-package channels between them) and one
module; integration sees it as one block. Grouped and per-block builds of the
same design give the same streams.
"""
import random
from pathlib import Path

import pytest

from xls_harness import REPO, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "compose"
FILES = [str(COMPOSE / "hier_pkg.sv"), str(COMPOSE / "mixed_pkg.sv")]
RTL_LIB = [REPO / "src" / "rtl" / n for n in ("fw_rv_fifo.sv", "fw_valid_check.sv",
                                             "fw_xls_fifo_wrapper.sv")]
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")


def _sim(tmp_path, design, inputs, seed=3):
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, inputs, seed))
    out = run_verilator(paths + RTL_LIB + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    return out


def test_group_partition():
    from fw.hdl.spl_flow import partition
    p = partition(FILES, "inner_top", ["add_k"], groups={"grp": ["add_k"]})
    (g,) = p.shell.children
    assert (g["name"], g["engine"], g["module"]) == ("grp", "xls", "grp")
    assert [m["name"] for m in g["group"]["members"]] == ["a", "b"]
    assert g["group"]["internal"] == [{"name": "ch", "depth": 1, "a": ["a", "out"],
                                       "b": ["b", "in"]}]
    assert [e["name"] for e in g["group"]["external"]] == ["a_in", "b_out"]
    assert p.shell.channels == []
    assert p.standalone() == {}


def test_unknown_group_is_an_error():
    from fw.hdl.spl_flow import XlsFlowError, partition
    with pytest.raises(XlsFlowError, match=r"island.groups \['g'\]"):
        partition(FILES, "inner_top", ["add_k"], groups={"g": ["nosuch"]})


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("top", ["inner_top", "mixed_top"])
def test_grouped_rtl_matches_reference(tmp_path, top):
    from fw.hdl.spl_flow import spl_to_rtl
    extern = {"ext_neg": {"signature": str(COMPOSE / "ext_neg_rtl.sig.json"),
                          "module": "ext_neg_rtl", "files": [str(COMPOSE / "ext_neg_rtl.sv")]}}
    design = spl_to_rtl(FILES, top, ["add_k"], extern=extern if top == "mixed_top" else None,
                        groups={"grp": ["add_k#(1)", "add_k#(2)"]})
    assert "grp.sv" in design.files
    assert "fw_xls_fifo_wrapper" in design.files["grp.sv"]
    xs = [r.randrange(256) for r in [random.Random(top)] for _ in range(120)]
    extra = [COMPOSE / "ext_neg_rtl.sv"] if top == "mixed_top" else []
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, {"in": xs}, 3))
    out = run_verilator(paths + extra + RTL_LIB + [tb], "xh_rtl_tb", tmp_path / "rtl",
                        with_lib=False, extra=["--assert", "+define+ASSERT_ON"])
    got = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    ref = (lambda x: (x + 3) & 0xff) if top == "inner_top" else \
        (lambda x: ((~((x + 3) & 0xff)) + 5) & 0xff)
    assert got == [ref(x) for x in xs]


# ---------------------------------------------------------------------------
# The reference design, per block and grouped (examples/resp_tracker).
# ---------------------------------------------------------------------------
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

DFM = REPO / "packages" / "python" / "bin" / "dfm"
EXAMPLE = REPO / "examples" / "resp_tracker"


@needs_xls
@pytest.mark.verilator
@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
@pytest.mark.parametrize("kset", ["k0", "k2"])
@pytest.mark.parametrize("grouped", [False, True], ids=["per_block", "grouped"])
def test_reference_design_grouped_and_per_block(tmp_path, kset, grouped):
    """Both builds pass the in-order contract against the class model, and
    each one's latency report equals its measured latency."""
    import zuspec.ir.core as ir
    from fw.hdl.verif.canon import Rule, check, compare
    from fw.hdl.xls_flow import sv_to_structure
    from test_resp_tracker import LAT_TB, _files, stimulus, trace
    from xls_harness import proc_testbench
    d = tmp_path / "rt"
    shutil.copytree(EXAMPLE, d, ignore=shutil.ignore_patterns("rundir"))
    name = kset
    if grouped:
        name = f"{kset}g"
        (d / "knobs" / f"{name}.yaml").write_text(
            f"base: {kset}.yaml\nisland:\n  groups:\n    rt_core: [rt_tag, rt_resp]\n")
    r = subprocess.run([str(DFM), "run", "all", "-D", f"kset={name}"], cwd=d,
                       capture_output=True, text=True, env=dict(os.environ))
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    rd = d / "rundir"
    part = json.loads((rd / "resp_tracker.part" / "partition.json").read_text())
    if grouped:
        assert [c["name"] for c in part["children"]] == ["rt_core"]
    rtl = _files(rd, "resp_tracker.top", "systemVerilogSource")
    (sig_path,) = _files(rd, "resp_tracker.top", "blockSignature")
    sig = ir.load_signature(str(sig_path))
    addrs = stimulus(seed=4)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(sig, {"req": addrs}, seed=3))
    out = run_verilator(rtl + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    rtl_outs = [int(l.split()[3], 16) for l in out if l.startswith("O rsp ")]
    pkg = _files(rd, "resp_tracker.knobs", "systemVerilogSource")
    files = [str(p) for p in pkg] + [str(d / "src" / "rt_pkg.sv")]
    comp = sv_to_structure(files, "rt_top").component
    mtb = tmp_path / "xh_proc_tb.sv"
    mtb.write_text(proc_testbench(["rt_pkg"], "rt_top", comp, {"req": addrs}))
    mout = run_verilator(files + [mtb], "xh_proc_tb", tmp_path / "model")
    model_outs = [int(l.split()[3], 16) for l in mout if l.startswith("O rsp ")]
    assert check(trace(addrs, rtl_outs), Rule()) == []
    assert compare(trace(addrs, model_outs), trace(addrs, rtl_outs), Rule(),
                   names=("model", "rtl")) == []
    rep = json.loads((rd / "resp_tracker.latency" / "latency.json").read_text())
    (path,) = [p for p in rep["paths"] if (p["src"], p["dst"]) == ("req", "rsp")]
    ltb = tmp_path / "xh_lat_tb.sv"
    ltb.write_text(LAT_TB)
    lout = run_verilator(rtl + [ltb], "xh_lat_tb", tmp_path / "lat", with_lib=False)
    (measured,) = [int(l.split()[1]) for l in lout if l.startswith("L ")]
    assert path["cycles"] == measured, (rep, measured)
