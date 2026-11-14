"""S5.3: the S3 sync classes through fe/elab/sync.py and be-sv match the
checked-in golden SV, which is Verilator ``-Wall`` clean and reads into
yosys through sv2v.

Set ``FW_UPDATE_GOLDEN=1`` to rewrite the golden on an intentional change.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import zuspec.ir.core as ir
from fw.hdl.config import FlowConfig
from fw.hdl.emit.be_sv import emit_sv
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab.sync import find_class_var, sync_component
from fw.hdl.fe.parser import Parser

GOLDEN = Path(__file__).parent / "golden" / "sync"

SV = '''
module t;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    fw_rv_slice #(bit [36:0]) s;
    fw_rv_pass  #(bit [7:0])  p;
endmodule
'''

CASES = [("s", "fw_rv_slice_w37"), ("p", "fw_rv_pass_w8")]


@pytest.fixture(scope="module")
def emitted(tmp_path_factory):
    d = tmp_path_factory.mktemp("emit_sync")
    f = d / "t.sv"
    f.write_text(SV)
    rep = ErrorReporter()
    p = Parser(FlowConfig(incdirs=[], defines={"FW_TRACE_OFF": "1"}, top_module="t"), rep)
    assert p.parse([str(f)], include_root=False), rep.errors()[:5]
    out = {}
    for var, name in CASES:
        comp = sync_component(find_class_var(p.compilation, "t", var), name)
        path = d / f"{name}.sv"
        path.write_text(emit_sv(ir.Context(type_m={name: comp})))
        out[name] = path
    return out


@pytest.mark.parametrize("name", [n for _, n in CASES])
def test_matches_golden(emitted, name):
    text = emitted[name].read_text()
    golden = GOLDEN / f"{name}.sv"
    if os.environ.get("FW_UPDATE_GOLDEN"):
        golden.write_text(text)
    assert text == golden.read_text()


def _need(*tools):
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        pytest.skip(f"not on PATH: {', '.join(missing)}")


@pytest.mark.parametrize("name", [n for _, n in CASES])
def test_verilator_lint_wall(name):
    _need("verilator")
    r = subprocess.run(["verilator", "--lint-only", "-Wall", str(GOLDEN / f"{name}.sv")],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "%Warning" not in r.stderr, r.stderr


@pytest.mark.parametrize("name", [n for _, n in CASES])
def test_sv2v_yosys_read(tmp_path, name):
    _need("sv2v", "yosys")
    v = tmp_path / f"{name}.v"
    r = subprocess.run(["sv2v", str(GOLDEN / f"{name}.sv")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    v.write_text(r.stdout)
    r = subprocess.run(["yosys", "-q", "-p",
                        f"read_verilog {v}; hierarchy -check -top {name}; proc; check -assert"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
