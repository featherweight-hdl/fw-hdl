"""The fw_sp_comb weaver (python/fw/hdl/weave/sp_comb.py, plan S6.1b): weave
sp_comb_pkg, build sp_comb_tb.sv with Verilator and check the declared fields
are comb after freeze_tree (one-channel views, a port of channels, an inherited
declaration, a generic class), that nothing is comb when the woven package is
not registered (teeth), and the weave-time errors."""
import os
import re
import subprocess

import pytest

from sv_weave.config import parse_config
from sv_weave.diag import SvWeaveError
from sv_weave.filelist import SourceSpec
from sv_weave.run import run

HERE = os.path.dirname(os.path.abspath(__file__))
FWHDL = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(FWHDL, "src")
INCDIRS = [SRC, os.path.join(SRC, "std")]
LIB = [os.path.join(SRC, f) for f in ("fw_clock_xtor_if.sv", "fw_clock_period_xtor_if.sv",
                                      "fw_hdl_pkg.sv")]
PKG = os.path.join(HERE, "sp_comb_pkg.sv")
CFG = """
sv-weave:
  binding: fw.hdl.weave.binding:FwHdlBinding
  plugin-path: [%s]
  weavers:
  - name: fw.hdl.weave.sp_comb:SpCombWeaver
""" % os.path.join(FWHDL, "python")


def _verilator():
    pk = os.path.join(FWHDL, "..", "verilator", "bin", "verilator")
    return pk if os.path.exists(pk) else "verilator"


def _weave(files, out):
    spec = SourceSpec()
    spec.files.extend(files)
    spec.incdirs.extend(INCDIRS)
    return run(parse_config(CFG, base_dir=FWHDL), spec=spec, out_dir=out)


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("sp_comb"))
    woven = _weave(LIB + [PKG], os.path.join(out, "woven"))
    files = LIB + [PKG] + [os.path.join(woven.out_dir, n) for n in woven.compile_order
                           if n.endswith("_woven.sv")] + [os.path.join(HERE, "sp_comb_tb.sv")]
    cmd = [_verilator(), "--binary", "--timing", "-Wno-fatal", "-Wno-lint", "-Wno-style",
           "--top-module", "sp_comb_tb", "-Mdir", os.path.join(out, "obj")] \
        + ["+incdir+" + d for d in INCDIRS] + files
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-3000:]
    exe = os.path.join(out, "obj", "Vsp_comb_tb")
    res = {}
    for tag, args in (("woven", []), ("bare", ["+no_init"])):
        r = subprocess.run([exe] + args, capture_output=True, text=True)
        assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
        res[tag] = dict(re.findall(r"^RESULT (\S+) (.*)$", r.stdout, re.M))
    res["text"] = woven.file("sp_comb_pkg_woven.sv").text
    return res


def test_flags(sim):
    # valid, ready, data
    assert sim["woven"] == {"a.o": "101", "a.i": "000", "a.p": "[a.*,b.valid]",
                            "s.o": "101", "s.j": "111", "s.p": "[a.*,b.valid]",
                            "g.g": "010"}


def test_teeth_unregistered(sim):
    assert sim["bare"] == {"a.o": "000", "a.i": "000", "a.p": "[]", "s.o": "000",
                           "s.j": "000", "s.p": "[]", "g.g": "000"}


def test_woven_calls(sim):
    t = sim["text"]
    assert 't.o.holder().set_comb("valid,data");' in t, t
    assert 't.p.set_comb("a.*,b.valid");' in t, t
    assert "t.j.holder().set_comb(\"*\");" in t, t
    assert "t.o.holder()" not in t.split("class fw_sp_comb__c_sub")[1].split("endclass")[0]


BAD = """
package bad_pkg;
    import fw_hdl_pkg::*;
    import sp_comb_pkg::*;
    class c_bad extends fw_component;
        %s
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
    endclass
endpackage
"""


@pytest.mark.parametrize("decl,msg", [
    ('(* fw_sp_comb = "x.valid" *) fw_rv_sp_out #(cbyte_t) o;',
     'c_bad.o: "x.valid": a one-channel port takes "f", "*" or "o.f"'),
    ('(* fw_sp_comb = "c.*" *) two_ch_port p;', 'no channel "c" in sp_comb_pkg::two_ch_port'),
    ('(* fw_sp_comb = "valid" *) two_ch_port p;', 'no channel "" in'),
    ('(* fw_sp_comb = " , " *) fw_rv_sp_out #(cbyte_t) o;', "c_bad.o: empty field list"),
    ('(* fw_sp_comb = "*" *) local fw_rv_sp_out #(cbyte_t) o;', "must be public"),
    ('(* fw_sp_comb = "*" *) int n;', "int is not a struct port"),
])
def test_errors(tmp_path, decl, msg):
    src = tmp_path / "bad_pkg.sv"
    src.write_text(BAD % decl)
    with pytest.raises(SvWeaveError) as e:
        _weave(LIB + [PKG, str(src)], str(tmp_path / "out"))
    assert msg in str(e.value), str(e.value)
