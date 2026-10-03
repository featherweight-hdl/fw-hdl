"""CH-2: the proc rows of xls-phase0.md §3.4 as SV component classes, run on
Verilator through a generated source/sink harness and in the interpreter on
the emitted XLS proc. Output streams and final property values must match."""
import random
import re
from pathlib import Path

import pytest

from fw.hdl.xls_flow import sv_to_xls
from zuspec.be.xls.printer import format_package
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main, run_codegen
from xls_harness import check_proc

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "micro" / "micro_proc_pkg.sv")


@pytest.mark.verilator
def test_p_acc(workdir):
    r = check_proc([PKG], "micro_proc_pkg", "p_acc", {"in": [3, 0, 7, 0, 1, 255, 255, 0]}, workdir)
    assert r.outputs["out"] == [8, 7, 511]


@pytest.mark.verilator
def test_p_temp(workdir):
    r = check_proc([PKG], "micro_proc_pkg", "p_temp", {"in": [1, 2, 3]}, workdir)
    # 116 would mean the temporary t leaked across activations
    assert r.outputs["out"] == [12, 114, 16]


@pytest.mark.verilator
def test_p_pred(workdir):
    rng = random.Random(7)
    a = [rng.getrandbits(8) for _ in range(40)]
    b = [rng.getrandbits(8) for _ in range(sum(x & 1 for x in a))]
    r = check_proc([PKG], "micro_proc_pkg", "p_pred", {"a": a, "b": b}, workdir)
    assert len(r.outputs["o"]) > 0


@pytest.mark.verilator
def test_p_frame_struct_payload(workdir):
    beats = []
    for k, n in enumerate([1, 2, 3, 4, 5]):
        for i in range(n):
            beats.append(((0x10 * k + i) << 1) | int(i == n - 1))
    r = check_proc([PKG], "micro_proc_pkg", "p_frame", {"in": beats}, workdir)
    assert len(r.outputs["out"]) == 1 + 1 + 2 + 2 + 3


@pytest.mark.verilator
def test_p_assert_stops_at_the_same_point(workdir):
    r = check_proc([PKG], "micro_proc_pkg", "p_assert", {"in": [1, 150, 7, 200, 3]},
                   workdir, expect_assert="x reached 200")
    assert r.outputs["out"] == [1, 150, 7]


@pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                    reason="needs opt_main and codegen_main")
def test_x1_5_source_positions_reach_the_verilog():
    # X1-5: with --source_annotation_strategy=comment, XLS codegen writes each
    # node's pos= into the Verilog. XLS prints it 0-based (as it does for DSLX),
    # so `// micro_proc_pkg.sv:L:C` names SV line L+1.
    pkg = sv_to_xls([PKG], "p_acc")
    res = run_codegen(format_package(pkg), extra=["--source_annotation_strategy=comment"])
    src = Path(PKG).read_text().splitlines()
    refs = re.findall(r"// (\S*micro_proc_pkg\.sv):(\d+):(\d+)", res.verilog)
    assert refs
    lines = {src[int(l)][int(c):] for _, l, c in refs}
    # the compare, the add and the put of p_acc's activation
    assert {"x == 0) begin", "sum + x;", "out.t.put(s);"} <= lines
