"""B4d: a design outside the static subset fails fw.hdl.xls.IR and
fw.hdl.spl.Partition with a located marker; neither task raises."""
import os
import subprocess
from pathlib import Path

import pytest

from xls_harness import REPO

HERE = Path(__file__).resolve().parent
SRC = HERE / "negative_dfm" / "twice_pkg.sv"
DFM = REPO / "packages" / "python" / "bin" / "dfm"

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
    assert "second operation on channel 'out'" in out, out[-3000:]
    assert "twice_pkg.sv:18" in out, out[-3000:]
