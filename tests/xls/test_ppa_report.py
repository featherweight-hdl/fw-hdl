"""xls_ppa.csv names the source line that dominates the critical path.

asap7, not unit: under the unit model every node costs 1 ps, so a receive and
its tuple_index bookkeeping can outweigh real logic."""
import csv
import os
import subprocess
from pathlib import Path

import pytest

from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DFM = REPO / "packages" / "python" / "bin" / "dfm"
SRC = HERE / "compose" / "crit_pkg.sv"

needs = pytest.mark.skipif(not DFM.exists() or codegen_main() is None or opt_main() is None,
                           reason="needs dfm, opt_main and codegen_main")

FLOW = """\
package:
  name: pp
  imports: [fw.hdl.spl, fw.hdl.report, synth.xls]
  tasks:
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {base}, include: [crit_pkg.sv]}}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src]
    with: {{top: crit_top, xls: [crit_blk]}}
  - {{name: rtl, uses: synth.xls.Codegen, needs: [part], with: {{pipeline_stages: {stages}, delay_model: asap7}}}}
  - {{name: ppa, uses: fw.hdl.report.Ppa, needs: [rtl]}}
"""


@needs
@pytest.mark.parametrize("stages", [1, 2])
def test_dominant_line_is_the_multiply_chain(tmp_path, stages):
    (tmp_path / "flow.yaml").write_text(FLOW.format(base=SRC.parent, stages=stages))
    r = subprocess.run([str(DFM), "run", "ppa"], cwd=tmp_path, capture_output=True,
                       text=True, env=dict(os.environ))
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    rows = list(csv.DictReader((tmp_path / "rundir" / "pp.ppa" / "xls_ppa.csv").open()))
    (row,) = rows
    crit_line = next(i for i, l in enumerate(SRC.read_text().splitlines(), 1) if "// CRIT" in l)
    assert row["block"] == "crit_blk" and int(row["stages"]) == stages
    assert row["crit_src"].endswith(f"crit_pkg.sv:{crit_line}"), row
    assert int(row["crit_ps"]) > 0 and 0 < int(row["crit_src_ps"]) <= int(row["crit_ps"])
    assert row["ii"] == "1"
