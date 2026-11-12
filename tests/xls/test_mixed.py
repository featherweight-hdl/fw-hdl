"""Mixed and nested children. A structural child integrates to a module
of its own; an extern child is RTL supplied with the design (a hand-written
module plus its block signature); XLS implements the rest. The integrated top
must lint, simulate and match the reference, two levels deep.
"""
import random
from pathlib import Path
from fw_tools import tool

import pytest

from xls_harness import REPO, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "compose"
FILES = [str(COMPOSE / "hier_pkg.sv"), str(COMPOSE / "mixed_pkg.sv")]
EXTERN = {"ext_neg": {"signature": str(COMPOSE / "ext_neg_rtl.sig.json"),
                      "module": "ext_neg_rtl", "files": [str(COMPOSE / "ext_neg_rtl.sv")]}}
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")


def reference(x):
    return ((~((x + 3) & 0xff)) + 5) & 0xff


def test_partition_tree():
    from fw.hdl.spl_flow import partition
    sh = partition(FILES, "deep_top", ["add_k"], extern=EXTERN).shell
    (m,) = sh.children
    assert (m["name"], m["engine"], m["module"]) == ("m", "structural", "mixed_top")
    kinds = {c["name"]: (c["engine"], c["module"]) for c in sh.nested(m).children}
    assert kinds["inner"] == ("structural", "inner_top")
    assert kinds["e"] == ("extern", "ext_neg_rtl")
    assert kinds["x"][0] == "xls"
    inner = next(c for c in sh.nested(m).children if c["name"] == "inner")
    assert [c["engine"] for c in sh.nested(m).nested(inner).children] == ["xls", "xls"]
    assert [s.module for s in sh.walk()] == ["deep_top", "mixed_top", "inner_top"]


def test_unassigned_leaf_names_both_engines():
    from fw.hdl.errors import FwHdlError
    from fw.hdl.spl_flow import partition
    with pytest.raises(FwHdlError, match=r"child 'e' \(ext_neg\) is not assigned to an engine"):
        partition(FILES, "mixed_top", ["add_k"])


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("top", ["mixed_top", "deep_top"])
def test_mixed_rtl_view(tmp_path, top):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, top, ["add_k"], extern=EXTERN)
    assert {"inner_top.sv", "mixed_top.sv"} <= set(design.files)
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    xs = [r.randrange(256) for r in [random.Random(top)] for _ in range(120)]
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, {"in": xs}, 9))
    lint = run_verilator(paths + [COMPOSE / "ext_neg_rtl.sv", REPO / "src" / "rtl" / "fw_rv_fifo.sv", tb],
                         "xh_rtl_tb", tmp_path / "rtl", with_lib=False,
                         extra=["--assert", "+define+ASSERT_ON", "-Wall", "-Wno-fatal"])
    got = [int(l.split()[3], 16) for l in lint if l.startswith("O out ")]
    assert got == [reference(x) for x in xs]


@needs_xls
def test_integrated_tops_lint_clean(tmp_path):
    """Verilator -Wall finds nothing in the modules integration writes (block
    bodies and the FIFO are linted where they are made)."""
    import subprocess
    from fw.hdl.spl_flow import spl_to_rtl
    from xls_harness import VERILATOR
    design = spl_to_rtl(FILES, "deep_top", ["add_k"], extern=EXTERN)
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
    r = subprocess.run([str(VERILATOR), "--lint-only", "-Wall", "--top-module", "deep_top",
                        *[str(tmp_path / n) for n in design.files],
                        str(COMPOSE / "ext_neg_rtl.sv"), str(REPO / "src" / "rtl" / "fw_rv_fifo.sv")],
                       capture_output=True, text=True, cwd=tmp_path)
    tops = ("deep_top.sv", "mixed_top.sv", "inner_top.sv", "ext_neg_rtl.sv")
    bad = [l for l in r.stderr.splitlines() if "%Warning" in l and any(t in l for t in tops)]
    errors = [l for l in r.stderr.splitlines()
              if l.startswith("%Error") and "Exiting due to" not in l]
    assert bad == [] and errors == [], r.stderr[-3000:]


DFM = tool("dfm")


@needs_xls
@pytest.mark.verilator
@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_mixed_through_dfm_tasks(tmp_path):
    """Partition -> Codegen -> Signature -> Integrate, the extern block named
    in the knob file (paths relative to it); the outputs simulate."""
    import json
    import os
    import shutil
    import subprocess
    for f in ("hier_pkg.sv", "mixed_pkg.sv", "ext_neg_rtl.sv", "ext_neg_rtl.sig.json"):
        shutil.copy(COMPOSE / f, tmp_path / f)
    (tmp_path / "knobs.yaml").write_text(
        "design:\n  top: deep_top\n  xls: [add_k]\n  extern:\n"
        "    ext_neg: {signature: ext_neg_rtl.sig.json, module: ext_neg_rtl,"
        " files: [ext_neg_rtl.sv]}\n"
        "xls:\n  default: {pipeline_stages: 1, delay_model: unit}\n")
    (tmp_path / "flow.yaml").write_text("""\
package:
  name: mixed
  imports: [fw.hdl.spl, fw.hdl.knobs, synth.xls, zuspec.xls]
  tasks:
  - name: knob-file
    uses: std.FileSet
    with: {type: fwKnobFile, include: [knobs.yaml]}
  - name: knobs
    uses: fw.hdl.knobs.Resolve
    needs: [knob-file]
  - name: src
    uses: std.FileSet
    with: {type: systemVerilogSource, include: [hier_pkg.sv, mixed_pkg.sv]}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src, knobs]
    with: {top: deep_top, xls: [add_k]}
  - name: rtl
    uses: synth.xls.Codegen
    needs: [part, knobs]
  - name: sig
    uses: zuspec.xls.Signature
    needs: [part, rtl]
  - name: top
    uses: fw.hdl.spl.Integrate
    needs: [part, sig, knobs]
""")
    r = subprocess.run([str(DFM), "run", "top"], cwd=tmp_path, capture_output=True, text=True,
                       env=dict(os.environ))
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    data = json.loads((tmp_path / "rundir" / "mixed.top" / "mixed.top.exec_data.json").read_text())
    srcs = [Path(fs["basedir"]) / f for fs in data["output"]["output"]
            if fs["filetype"] == "systemVerilogSource" for f in fs["files"]]
    names = [p.name for p in srcs]
    assert {"ext_neg_rtl.sv", "inner_top.sv", "mixed_top.sv", "deep_top.sv"} <= set(names)
    assert names.index("inner_top.sv") < names.index("mixed_top.sv") < names.index("deep_top.sv")
    import zuspec.ir.core as ir
    (sig,) = [Path(fs["basedir"]) / f for fs in data["output"]["output"]
              if fs["filetype"] == "blockSignature" for f in fs["files"]]
    xs = [r.randrange(256) for r in [random.Random(3)] for _ in range(60)]
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(ir.load_signature(str(sig)), {"in": xs}, 4))
    out = run_verilator(srcs + [tb], "xh_rtl_tb", tmp_path / "sim", with_lib=False)
    got = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    assert got == [reference(x) for x in xs]
