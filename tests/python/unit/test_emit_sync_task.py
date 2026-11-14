"""S5.4: ``fw.hdl.emit.sync.emit_sync`` and the ``fw.hdl.sync.Emit`` task
(``dfm_tasks.SyncEmit``) emit one module per class variable of the top,
named after the variable, matching the S5.3 golden."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from fw.hdl.dfm_tasks import SyncEmit
from fw.hdl.emit.sync import emit_sync

GOLDEN = Path(__file__).parent / "golden" / "sync"

SV = '''
module t;
    import fw_std_pkg::*;
    fw_rv_slice #(bit [36:0]) fw_rv_slice_w37;
    fw_rv_pass  #(bit [7:0])  fw_rv_pass_w8;
    int n;
endmodule
'''


@pytest.fixture
def top(tmp_path):
    f = tmp_path / "t.sv"
    f.write_text(SV)
    return f


def test_emit_sync_all(top):
    out = emit_sync([str(top)], "t")
    assert list(out) == ["fw_rv_slice_w37", "fw_rv_pass_w8"]
    for name, text in out.items():
        assert text == (GOLDEN / f"{name}.sv").read_text()


def test_emit_sync_vars(top):
    assert list(emit_sync([str(top)], "t", vars=["fw_rv_pass_w8"])) == ["fw_rv_pass_w8"]


def test_task(top, tmp_path):
    rundir = tmp_path / "run"
    fs = SimpleNamespace(filetype="systemVerilogSource", basedir=str(top.parent),
                         files=[top.name], incdirs=[], defines=[])
    inp = SimpleNamespace(name="emit", rundir=str(rundir), inputs=[fs],
                          params=SimpleNamespace(top="t", vars=[]))
    res = asyncio.run(SyncEmit(None, inp))
    assert res.status == 0, res.markers
    assert res.output[0].files == ["fw_rv_slice_w37.sv", "fw_rv_pass_w8.sv"]
    assert ((rundir / "fw_rv_slice_w37.sv").read_text()
            == (GOLDEN / "fw_rv_slice_w37.sv").read_text())


def test_task_error(top, tmp_path):
    fs = SimpleNamespace(filetype="systemVerilogSource", basedir=str(top.parent),
                         files=[top.name], incdirs=[], defines=[])
    inp = SimpleNamespace(name="emit", rundir=str(tmp_path / "run"), inputs=[fs],
                          params=SimpleNamespace(top="t", vars=["n"]))
    res = asyncio.run(SyncEmit(None, inp))
    assert res.status == 1 and res.markers
