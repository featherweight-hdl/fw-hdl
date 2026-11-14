"""The settle weaver (python/fw/hdl/weave/settle.py, plan S4.2): golden tables
for the S3 classes and the synthetic ones in weave/settle_syn_pkg.sv, a Verilator
lint of the woven packages, and the diagnostics.

Goldens are refreshed with FW_SETTLE_REGEN=1 and reviewed in the diff."""
import os
import shutil
import subprocess

import pytest

from sv_weave.config import parse_config
from sv_weave.diag import SvWeaveError
from sv_weave.filelist import SourceSpec
from sv_weave.run import run

HERE = os.path.dirname(os.path.abspath(__file__))
FWHDL = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(FWHDL, "src")
GOLDEN = os.path.join(HERE, "weave", "golden")
INCDIRS = [SRC, os.path.join(SRC, "std")]
LIB = [os.path.join(SRC, f) for f in ("fw_clock_xtor_if.sv", "fw_clock_period_xtor_if.sv",
                                      "fw_hdl_pkg.sv", os.path.join("std", "fw_std_pkg.sv"))]
SOURCES = LIB + [os.path.join(HERE, "weave", "settle_syn_pkg.sv")]
CFG = """
sv-weave:
  binding: fw.hdl.weave.binding:FwHdlBinding
  plugin-path: [%s]
  weavers:
  - name: fw.hdl.weave.settle:SettleWeaver
""" % os.path.join(FWHDL, "python")


def _run(files, out):
    spec = SourceSpec()
    spec.files.extend(files)
    spec.incdirs.extend(INCDIRS)
    return run(parse_config(CFG, base_dir=FWHDL), spec=spec, out_dir=out)


@pytest.fixture(scope="module")
def woven(tmp_path_factory):
    return _run(SOURCES, str(tmp_path_factory.mktemp("woven")))


@pytest.mark.parametrize("pkg", ["fw_std_pkg_woven", "settle_syn_pkg_woven"])
def test_golden(woven, pkg):
    text = woven.file(pkg + ".sv").text
    path = os.path.join(GOLDEN, pkg + ".sv")
    if os.environ.get("FW_SETTLE_REGEN"):
        with open(path, "w") as fp:
            fp.write(text)
    with open(path) as fp:
        assert text == fp.read(), "woven output differs from %s (FW_SETTLE_REGEN=1)" % path


def test_nowrite_warning(woven):
    msgs = [str(d) for d in woven.diags]
    assert any("syn_nowrite.comb() writes no port field" in m for m in msgs), msgs
    assert not any("syn_helper" in m or "fw_rv_pass" in m for m in msgs), msgs


BAD = """
package settle_bad_pkg;
    import fw_hdl_pkg::*;
    class syn_bad extends fw_component implements fw_combinational;
        fw_sig #(bit) a;
        function new(string name, fw_component parent);
            super.new(name, parent);
            a = new("a");
        endfunction
        virtual function void comb();
            a.set_reset_force(1);
        endfunction
    endclass
endpackage
"""


def test_opaque_in_comb_is_error(tmp_path):
    src = tmp_path / "settle_bad_pkg.sv"
    src.write_text(BAD)
    with pytest.raises(SvWeaveError) as ex:
        _run(LIB + [str(src)], str(tmp_path / "out"))
    text = str(ex.value) + repr(getattr(ex.value, "__dict__", ""))
    assert "syn_bad.comb() calls a.set_reset_force" in text, text


def _verilator():
    pk = os.path.join(FWHDL, "..", "verilator", "bin", "verilator")
    return pk if os.path.exists(pk) else shutil.which("verilator")


LINT_TOP = """
module lint_top;
    import fw_std_pkg_woven::*;
    import settle_syn_pkg_woven::*;
endmodule
"""


@pytest.mark.skipif(_verilator() is None, reason="verilator not found")
def test_lint(woven, tmp_path):
    top = tmp_path / "lint_top.sv"
    top.write_text(LINT_TOP)
    files = SOURCES + [os.path.join(woven.out_dir, n) for n in woven.compile_order
                       if n.endswith("_woven.sv")] + [str(top)]
    cmd = [_verilator(), "--lint-only", "-Wall", "-Wno-fatal", "-Wno-UNUSEDPARAM",
           "-Wno-UNUSEDSIGNAL", "-Wno-UNDRIVEN", "--top-module", "lint_top"] \
        + ["+incdir+" + d for d in INCDIRS] + files
    r = subprocess.run(cmd, capture_output=True, text=True)
    woven_msgs = [l for l in r.stderr.splitlines() if "_woven.sv" in l]
    assert r.returncode == 0 and not woven_msgs, r.stderr[-3000:]


UNIT = """
typedef logic [7:0] u8_t;
class unit_user;
    fw_std_pkg::fw_rv_pass #(u8_t) p8;
endclass
"""


def test_unit_typedef_args(tmp_path):
    """A specialization by a $unit typedef (plan S4.3b2): the woven package
    cannot name the typedef, so it is spelled as its integral type. (A struct
    typedef would get no matcher, with a warning; untested, since the boundary
    summary does not yet cover holders specialized by a $unit struct.)"""
    src = tmp_path / "unit_user.sv"
    src.write_text(UNIT)
    w = _run(LIB + [str(src)], str(tmp_path / "out"))
    text = open(os.path.join(w.out_dir, "fw_std_pkg_woven.sv")).read()
    assert "fw_settle_is #(fw_std_pkg::fw_rv_pass#(logic[7:0]))" in text, text
    assert "u8_t" not in text, text
