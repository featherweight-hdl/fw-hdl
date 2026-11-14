"""The settle scheduler (src/sync/fw_settle_sched.svh, plan S4.3b): weave
settle_chain_pkg with the settle weaver, build settle_tb.sv with Verilator and
check (a) a 5-stage comb chain built in reverse order takes 5 comb()
evaluations per edge, and (d) a chain with an un-woven class falls back and
gives the naive kernel's values, (b) a comb() serving two independent paths
through another is a false cycle, settles and is reported, and (c) a true loop
is fatal naming its fields unless waived."""
import os
import re
import subprocess

import pytest

from sv_weave.config import parse_config
from sv_weave.filelist import SourceSpec
from sv_weave.run import run

HERE = os.path.dirname(os.path.abspath(__file__))
FWHDL = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(FWHDL, "src")
INCDIRS = [SRC, os.path.join(SRC, "std")]
LIB = [os.path.join(SRC, f) for f in ("fw_clock_xtor_if.sv", "fw_clock_period_xtor_if.sv",
                                      "fw_hdl_pkg.sv", os.path.join("std", "fw_std_pkg.sv"))]
PKG = os.path.join(HERE, "settle_chain_pkg.sv")
CFG = """
sv-weave:
  binding: fw.hdl.weave.binding:FwHdlBinding
  plugin-path: [%s]
  weavers:
  - name: fw.hdl.weave.settle:SettleWeaver
""" % os.path.join(FWHDL, "python")


def _verilator():
    pk = os.path.join(FWHDL, "..", "verilator", "bin", "verilator")
    return pk if os.path.exists(pk) else "verilator"


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("settle"))
    spec = SourceSpec()
    spec.files.extend(LIB + [PKG])
    spec.incdirs.extend(INCDIRS)
    woven = run(parse_config(CFG, base_dir=FWHDL), spec=spec, out_dir=os.path.join(out, "woven"))
    files = LIB + [PKG] + [os.path.join(woven.out_dir, n) for n in woven.compile_order
                           if n.endswith("_woven.sv")] + [os.path.join(HERE, "settle_tb.sv")]
    cmd = [_verilator(), "--binary", "--timing", "-Wno-fatal", "-Wno-lint", "-Wno-style",
           "--top-module", "settle_tb", "-Mdir", os.path.join(out, "obj")] \
        + ["+incdir+" + d for d in INCDIRS] + files
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-3000:]
    exe = os.path.join(out, "obj", "Vsettle_tb")
    r = subprocess.run([exe, "+fw_settle_show"], capture_output=True, text=True)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    res = dict(re.findall(r"^RESULT (\S+) (\S+)$", r.stdout, re.M))
    res["stdout"] = r.stdout
    c = subprocess.run([exe, "+settle_case_c"], capture_output=True, text=True)
    res["c_unwaived.rc"] = c.returncode
    res["c_unwaived.out"] = c.stdout + c.stderr
    return res


def test_a_chain_five_evals(results):
    assert results["a.fallback"] == "0"
    assert results["a.evals"] == "5"
    assert results["a.vals"] == results["a_naive.vals"]
    assert int(results["a_naive.evals"]) > 5


def test_d_unwoven_falls_back(results):
    assert results["d.fallback"] == "1"
    assert results["d.vals"] == results["d_naive.vals"] == results["a.vals"]


def test_b_false_cycle(results):
    assert results["b.kind"] == "false_cycle"
    assert results["b.vals"] == results["b_naive.vals"] == results["a.vals"]
    show = results["stdout"]
    assert re.search(r"group \d+: false cycle: b\.a, b\.b\n    fields: b\.a\.o0\.valid, b\.a\.i1\.valid", show), show


def test_c_true_loop(results):
    assert results["c.kind"] == "true_loop"
    assert results["c.waiver"] == "yes"
    assert "waived: test ring" in results["stdout"]
    assert results["c_unwaived.rc"] != 0
    out = results["c_unwaived.out"]
    assert "RESULT c_unwaived.kind" not in out
    assert re.search(r"comb loop through c_unwaived\.w\d\.\w\.valid -> c_unwaived\.w\d\.\w\.valid -> "
                     r"c_unwaived\.w\d\.\w\.valid \(comb\(\) of c_unwaived\.w1, c_unwaived\.w2\)", out), out
