"""B4d: a design outside the static subset fails fw.hdl.xls.IR and
fw.hdl.spl.Partition with a located marker; neither task raises."""
import json
import os
import subprocess
from pathlib import Path
from fw_tools import tool

import pytest

from xls_harness import REPO

HERE = Path(__file__).resolve().parent
SRC = HERE / "negative_dfm" / "twice_pkg.sv"
DFM = tool("dfm")

FLOW = """\
package:
  name: neg
  imports: [fw.hdl.xls, fw.hdl.spl]
  tasks:
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {base}, include: [twice_pkg.sv]}}
  - name: ir
    uses: fw.hdl.xls.IR
    needs: [src]
    with: {{top: [twice]}}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src]
    with: {{top: twice_top, xls: [twice]}}
"""


@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
@pytest.mark.parametrize("task", ["ir", "part"])
def test_lowering_error_is_a_located_marker(tmp_path, task):
    (tmp_path / "flow.yaml").write_text(FLOW.format(base=SRC.parent))
    r = subprocess.run([str(DFM), "run", task], cwd=tmp_path, capture_output=True,
                       text=True, env=dict(os.environ))
    out = r.stdout + r.stderr
    assert r.returncode != 0, out
    assert "Task threw exception" not in out, out[-3000:]
    # The location is checked in the task's recorded markers, not in the
    # console: dfm's console wraps long paths at the terminal width.
    data = json.loads((tmp_path / "rundir" / f"neg.{task}" /
                       f"neg.{task}.exec_data.json").read_text())
    markers = data["result"]["markers"]
    m = next((m for m in markers if "second operation on channel 'out'" in m["msg"]),
             None)
    assert m is not None, markers
    assert m["severity"] == "error", m
    assert Path(m["loc"]["path"]).name == "twice_pkg.sv" and m["loc"]["line"] == 18, m
