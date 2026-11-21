"""Micro-pipelining D0 spike F6 (python/fw/hdl/spikes/pipeline.py): a
recognized map made K stages deep with a stall controller, Zuspec IR to
Zuspec IR, emitted by zuspec-be-sv unchanged. (The generated RTL is checked
against the hand-written answer key by examples/rr_merge_pipe/scripts/
equiv_auto.sh, and on the bench and with SBY there.)"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

import zuspec.ir.core as ir
from fw.hdl.emit.be_sv import emit_sv
from fw.hdl.spikes.dataflow import MapMatch, match_map
from fw.hdl.spikes.pipeline import pipeline_design, project_class, stall_map

EX = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                  "examples", "rr_merge_pipe"))


@pytest.fixture(scope="module")
def v0():
    sys.path.insert(0, os.path.join(EX, "scripts"))
    try:
        from gen_rtl import FILES, INCDIRS
    finally:
        sys.path.pop(0)
    from fw.hdl.emit.sync import elab_sync_param
    return elab_sync_param(FILES, "rr_merge_pipe_emit_top", incdirs=INCDIRS,
                           vars=["rr_merge_pipe"])["rr_merge_pipe"]


@pytest.mark.parametrize("k", [1, 2, 3])
def test_stall_fields(v0, k):
    m = match_map(v0["pipe_map_in"])
    assert isinstance(m, MapMatch)
    c = stall_map(m, k)
    names = [f.name for f in c.fields]
    assert names[:2] == ["clock", "reset"]
    assert [n for n in names if n.startswith("s")] == \
        [x for s in range(1, k + 1) for x in (f"s{s}_v", f"s{s}_d")]
    assert all(f.drive == ir.ProcessKind.SYNC for f in c.fields if f.name.startswith("s"))
    assert len(c.comb_processes) == 1 and len(c.sync_processes) == 1


def test_design_emits_and_lints(v0, tmp_path):
    m = match_map(v0["pipe_map_in"])
    out = pipeline_design(v0, "rr_merge_pipe", "min", m, 2, "auto2")
    assert list(out)[-1] == "auto2"
    mi = next(x for x in out["auto2"].module_instances if x.name == "min")
    assert mi.module == "pipe_map_in_stall2"
    assert [c.port for c in mi.connections[:2]] == ["clock", "reset"]
    sv = emit_sv(ir.Context(type_m=out))
    assert "module pipe_map_in_stall2" in sv and "s2_v" in sv
    if shutil.which("verilator") is None:
        pytest.skip("no verilator")
    f = tmp_path / "auto2.sv"
    f.write_text(sv)
    r = subprocess.run(["verilator", "--lint-only", "-Wall", "-Wno-DECLFILENAME", "-Wno-WIDTH",
                        "-Wno-UNUSEDSIGNAL", "--top-module", "auto2", str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_projection(v0):
    m = match_map(v0["pipe_map_in"])
    out = pipeline_design(v0, "rr_merge_pipe", "min", m, 1, "auto1")
    txt = project_class(out["pipe_map_in_stall1"], out)
    assert "fw_rv_sp_in #(TI) in[N];" in txt
    assert "out[i].set_valid(s1_v[i]);" in txt
    assert "s1_d[i] = f(in[i].get_data());" in txt
