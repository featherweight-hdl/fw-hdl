"""A register block as a child (``fw_reg_component``).

The child takes software writes on a stream and drives level channels from
its registers; in RTL it is the generated regblock core under a wrapper. The
class model and the RTL give the same stream once the writes have landed;
the generated modules lint clean; a level port no register drives, and a
register hardware writes, are rejected at the SV line.
"""
import json
import os
import random
import shutil
import subprocess
from pathlib import Path
from fw_tools import tool

import pytest

from fw.hdl.verif.canon import Event, Rule, compare
from fw.hdl.xls_flow import sv_to_structure
from xls_harness import REPO, VERILATOR, proc_testbench, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "compose"
FILES = [str(COMPOSE / "regs_pkg.sv")]
RTL_LIB = [REPO / "src" / "rtl" / "fw_rv_fifo.sv"]
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")
DFM = tool("dfm")

K, LO = 0x29, 0x5c
#: {addr, data} writes: k, then p (hi is not read)
CFG = [(0 << 32) | K, (4 << 32) | (0xbeef << 16) | LO]


def reference(xs):
    return [((x + K) & 0xff) ^ LO for x in xs]


def _trace(want, outs):
    ev = [Event("in", "in", i, i, data=w) for i, w in enumerate(want)]
    ev += [Event("out", "out", len(want) + j, j, data=v) for j, v in enumerate(outs)]
    return ev


def test_register_child_is_native():
    from fw.hdl.spl_flow import partition
    part = partition(FILES, "rtop", ["kadd"])
    (rc,) = [c for c in part.shell.children if c["name"] == "rc"]
    assert rc["engine"] == "native"
    assert rc["native"] == {"kind": "regblock", "block": "rk_regs", "W": 32, "AW": 16,
                            "levels": {"k": "k", "p": "p"}}
    assert {c["name"]: c["kind"] for c in part.shell.channels} == {"kl": "level", "pl": "level"}
    assert list(part.blocks) == ["kadd"]        # the native child is not an XLS block


@needs_xls
@pytest.mark.verilator
def test_register_child_model_and_rtl_agree(tmp_path):
    from fw.hdl.spl_flow import spl_to_rtl
    rng = random.Random(9)
    xs = [rng.randrange(256) for _ in range(80)]
    inputs = {"cfg": CFG, "in": xs}
    want = reference(xs)

    comp = sv_to_structure(FILES, "rtop").component
    tb = tmp_path / "xh_proc_tb.sv"
    tb.write_text(proc_testbench(["regs_pkg"], "rtop", comp, inputs, after={"in": "cfg"}))
    mout = run_verilator(FILES + [tb], "xh_proc_tb", tmp_path / "model")
    model = [int(l.split()[3], 16) for l in mout if l.startswith("O out ")]

    design = spl_to_rtl(FILES, "rtop", ["kadd"])
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, inputs, seed=6, after={"in": "cfg"}))
    rout = run_verilator(paths + RTL_LIB + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False)
    rtl = [int(l.split()[3], 16) for l in rout if l.startswith("O out ")]

    assert model == want
    assert compare(_trace(want, model), _trace(want, rtl), Rule(), names=("model", "rtl")) == []


@needs_xls
def test_register_child_reset_values_reach_the_levels(tmp_path):
    """No writes: the levels carry the registers' reset values (k=3, p.lo=0x11)
    in both views."""
    from fw.hdl.spl_flow import spl_to_rtl
    xs = list(range(20))
    want = [((x + 3) & 0xff) ^ 0x11 for x in xs]
    comp = sv_to_structure(FILES, "rtop").component
    tb = tmp_path / "xh_proc_tb.sv"
    tb.write_text(proc_testbench(["regs_pkg"], "rtop", comp, {"in": xs}))
    mout = run_verilator(FILES + [tb], "xh_proc_tb", tmp_path / "model")
    assert [int(l.split()[3], 16) for l in mout if l.startswith("O out ")] == want
    design = spl_to_rtl(FILES, "rtop", ["kadd"])
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    tb = tmp_path / "xh_rtl_tb.sv"
    # the XLS block's level inputs are registered: the first item may see 0
    tb.write_text(rtl_testbench(design.signature, {"in": xs}, seed=2))
    rout = run_verilator(paths + RTL_LIB + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False)
    got = [int(l.split()[3], 16) for l in rout if l.startswith("O out ")]
    assert got[2:] == want[2:]


@needs_xls
def test_register_child_lints_clean(tmp_path):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, "rtop", ["kadd"])
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
    r = subprocess.run([str(VERILATOR), "--lint-only", "-Wall", "--top-module", "rtop",
                        *[str(tmp_path / n) for n in design.files], *map(str, RTL_LIB)],
                       capture_output=True, text=True, cwd=tmp_path)
    mine = ("rtop.sv", "rk_rc.sv")
    bad = [l for l in r.stderr.splitlines() if "%Warning" in l and any(t in l for t in mine)]
    errors = [l for l in r.stderr.splitlines()
              if l.startswith("%Error") and "Exiting due to" not in l]
    assert bad == [] and errors == [], r.stderr[-3000:]


NEG = """\
package neg_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    class n_regs extends fw_reg_block #(32);
        fw_reg #(bit [31:0]) a;
        fw_reg #(bit [31:0]) s;
        function new(string name);
            super.new(name);
            a = new("a", this);
            s = new("s", this, .hw_wmask('1));
        endfunction
    endclass
    class n_rc extends fw_reg_component #(n_regs);
        fw_port #(fw_level_set_if #(bit [31:0])) a;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        virtual function void build();
            super.build();
            a = new("a", this);
        endfunction
        function void connect();
            DRIVE
        endfunction
    endclass
    class n_use extends fw_component implements fw_runnable;
        fw_port #(fw_level_if #(bit [31:0])) a;
        fw_port #(fw_put_if #(bit [31:0]))   out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            a = new("a", this);
            out = new("out", this);
        endfunction
        virtual task run();
            forever out.t.put(a.t.get());
        endtask
    endclass
    class n_top extends fw_component;
        fw_port #(fw_get_if #(bit [47:0])) cfg;
        fw_port #(fw_put_if #(bit [31:0])) out;
        n_rc                               rc;
        n_use                              u;
        fw_level_channel #(bit [31:0])     al;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            cfg = new("cfg", this);
            out = new("out", this);
            rc = new("rc", this);
            u = new("u", this);
            al = new("al", this);
        endfunction
        function void connect();
            rc.wr.connect(cfg);
            rc.a.connect(al.put_ex);
            u.a.connect(al.get_ex);
            u.out.connect(out);
        endfunction
    endclass
endpackage
"""


@pytest.mark.parametrize("drive, msg", [
    ("", "rc.a: no register drives it"),
    ("drive(fw_reg_level #(bit [31:0])::make(blk.s, a));", "written by hardware"),
])
def test_register_child_negatives(tmp_path, drive, msg):
    from fw.hdl.errors import FwHdlError
    from fw.hdl.spl_flow import partition
    f = tmp_path / "neg_pkg.sv"
    f.write_text(NEG.replace("DRIVE", drive))
    with pytest.raises(FwHdlError) as e:
        partition([str(f)], "n_top", ["n_use"])
    assert msg in str(e.value) and "neg_pkg.sv:" in str(e.value), str(e.value)


@needs_xls
@pytest.mark.verilator
@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_register_child_through_dfm_tasks(tmp_path):
    """Partition writes the native module and its signature; Integrate picks
    them up as it does an extern block, and the outputs simulate."""
    import zuspec.ir.core as ir
    shutil.copy(COMPOSE / "regs_pkg.sv", tmp_path / "regs_pkg.sv")
    (tmp_path / "flow.yaml").write_text("""\
package:
  name: regs
  imports: [fw.hdl.spl, synth.xls, zuspec.xls]
  tasks:
  - name: src
    uses: std.FileSet
    with: {type: systemVerilogSource, include: [regs_pkg.sv]}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src]
    with: {top: rtop, xls: [kadd]}
  - name: rtl
    uses: synth.xls.Codegen
    needs: [part]
  - name: sig
    uses: zuspec.xls.Signature
    needs: [part, rtl]
  - name: top
    uses: fw.hdl.spl.Integrate
    needs: [part, sig]
""")
    r = subprocess.run([str(DFM), "run", "top"], cwd=tmp_path, capture_output=True, text=True,
                       env=dict(os.environ))
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    data = json.loads((tmp_path / "rundir" / "regs.top" / "regs.top.exec_data.json").read_text())
    srcs = [Path(fs["basedir"]) / f for fs in data["output"]["output"]
            if fs["filetype"] == "systemVerilogSource" for f in fs["files"]]
    assert "rk_rc.sv" in [p.name for p in srcs]
    (sig,) = [Path(fs["basedir"]) / f for fs in data["output"]["output"]
              if fs["filetype"] == "blockSignature" for f in fs["files"]]
    rng = random.Random(4)
    xs = [rng.randrange(256) for _ in range(40)]
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(ir.load_signature(str(sig)), {"cfg": CFG, "in": xs}, 4,
                                after={"in": "cfg"}))
    out = run_verilator(srcs + [tb], "xh_rtl_tb", tmp_path / "sim", with_lib=False)
    assert [int(l.split()[3], 16) for l in out if l.startswith("O out ")] == reference(xs)
