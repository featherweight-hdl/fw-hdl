"""Run the synchronous-logic SVUnit self-test (tests/sync/flow.yaml) through
dfm. The fragment is wrapped in a throwaway package so the run does not depend
on loading the whole root flow."""
import os
import subprocess
from pathlib import Path
from fw_tools import tool

import pytest

HERE = Path(__file__).resolve().parent
DFM = tool("dfm")


@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_fw_sync_selftest(tmp_path):
    (tmp_path / "flow.yaml").write_text(
        "package:\n  name: syn\n  imports: [hdlsim, hdlsim.vlt, hdltest.svunit]\n"
        f"  fragments: [{HERE / 'flow.yaml'}]\n")
    r = subprocess.run([str(DFM), "run", "sync.selftest"], cwd=tmp_path,
                       capture_output=True, text=True, env=dict(os.environ))
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    assert "SVUnit pass: 23 of 23 tests passing" in out, out[-3000:]
