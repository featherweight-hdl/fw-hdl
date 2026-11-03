"""Run the library classes' SVUnit tests (tests/stdlib/flow.yaml) through
dfm. The fragment is wrapped in a throwaway package with the library's own
fragment, so the run does not depend on loading the whole root flow."""
import os
import re
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DFM = REPO / "packages" / "python" / "bin" / "dfm"


@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_stdlib_unit(tmp_path):
    (tmp_path / "flow.yaml").write_text(
        "package:\n  name: lib\n  imports: [hdlsim, hdlsim.vlt, hdltest.svunit]\n"
        f"  fragments: [{REPO / 'src' / 'flow.yaml'}, {HERE / 'flow.yaml'}]\n")
    r = subprocess.run([str(DFM), "run", "stdlib.unit"], cwd=tmp_path,
                       capture_output=True, text=True, env=dict(os.environ))
    out = r.stdout + r.stderr
    (REPO / "build").mkdir(exist_ok=True)
    (REPO / "build" / "stdlib-unit.log").write_text(out)
    assert r.returncode == 0, out[-3000:]
    m = re.search(r"SVUnit pass: (\d+) of (\d+) tests passing", out)
    assert m and m.group(1) == m.group(2) and int(m.group(2)) >= 6, out[-3000:]
