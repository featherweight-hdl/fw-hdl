"""fw_sp_mem: an array of a step class held in a single-port RAM.

* mm_rw (mem/mem_pkg.sv) reads and writes a 16-word memory from a command
  stream; the class model, a Python model of the RAM's timing, and XLS's RTL
  with fw_ram_1rw_model on the memory's ports agree cycle for cycle, at 1 and
  2 stages.
* In a design (mm_top): the knob ``storage:`` binds ``u.mem`` to flops, an
  SRAM macro shim or a wrapper; Integrate places that RAM beside the block,
  and the response stream is the same, cycle for cycle, for each.
* The frontend: the member is two ports, ``mem_req`` (valid-only {we, a, wd})
  and ``mem_rd`` (a level), and the request and the read data are kept in one
  stage. A step with a memory cannot stall.
"""
import random
from pathlib import Path

import pytest

from fw.hdl.errors import FwHdlError
from fw.hdl.xls_flow import XlsFlowError, sv_to_component
from xls_harness import REPO, check_step, have_verilator, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "mem" / "mem_pkg.sv")
needs_sim = pytest.mark.skipif(not have_verilator(), reason="needs Verilator")
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")
CYCLES = 160


def cmd(wr, a, d=0):
    return (wr << 20) | (a << 16) | d


def schedule(seed, n=120):
    """Writes first to every word (a RAM's unwritten word is unknown), then a
    mix of reads and writes, one offered per cycle from cycle 1."""
    rng = random.Random(seed)
    cmds = [cmd(1, a, rng.randrange(1 << 16)) for a in range(16)]
    for _ in range(n):
        cmds.append(cmd(rng.random() < 0.4, rng.randrange(16), rng.randrange(1 << 16)))
    return {"cmd": [(i + 1, c) for i, c in enumerate(cmds)]}


def ref(sched, cycles):
    """mm_rw on a RAM with a 1-cycle read: a read's word goes to rsp the next
    cycle."""
    mem = [0] * 16
    q = list(sched["cmd"])
    out, pend, rd = [], False, 0
    for c in range(cycles):
        if pend:
            out.append((c, rd))
        pend = False
        if q and q[0][0] <= c:
            _, v = q.pop(0)
            a = (v >> 16) & 0xf
            if v >> 20:
                mem[a] = v & 0xffff
            else:
                rd, pend = mem[a], True
    return {"rsp": out} if out else {}


def test_member_is_two_ports():
    comp = sv_to_component([PKG], "mm_rw")
    ports = {f.name: f.pragmas for f in comp.fields if f.pragmas.get("fw_mem")}
    assert set(ports) == {"mem_req", "mem_rd"}
    assert ports["mem_req"]["fw_flow"] == "valid"
    assert ports["mem_rd"]["fw_flow"] == "level"
    assert ports["mem_req"]["fw_mem"]["addr_bits"] == 4
    from zuspec.be.xls.lower_proc import codegen_flags, lower_component
    flags = codegen_flags(comp, lower_component(comp))
    assert any("mem_rd:recv:mem_req:send:0:0" in f for f in flags)


def test_step_with_memory_cannot_stall():
    with pytest.raises(FwHdlError, match="uses a memory .*cannot stall"):
        sv_to_component([PKG], "mm_bad_stall")


@needs_sim
@pytest.mark.verilator
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_model_ref_and_rtl_agree(tmp_path, seed):
    sched = schedule(seed)
    got = check_step([PKG], "mem_pkg", "mm_rw", sched, CYCLES, tmp_path, rtl_stages=(1, 2))
    assert got == ref(sched, CYCLES)


# --- in a design: the RAM beside the block, by its storage binding ------------
FILES = [PKG]
RAM_LIB = [REPO / "src" / "rtl" / n for n in ("fw_rv_fifo.sv", "fw_valid_check.sv",
                                                "fw_ram_1rw_model.sv")]
SHIM = HERE / "mem" / "mm_ram_shim.sv"


def stream_ref(cmds):
    mem, out = [0] * 16, []
    for v in cmds:
        a = (v >> 16) & 0xf
        if v >> 20:
            mem[a] = v & 0xffff
        else:
            out.append(mem[a])
    return out


def _design(tmp_path, storage, seed=4):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, "mm_top", ["mm_rw"], storage=storage)
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    cmds = [c for _, c in schedule(seed)["cmd"]]
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, {"cmd": cmds}, seed, throttle=1, cycles=True))
    out = run_verilator(paths + RAM_LIB + [SHIM, tb], "xh_rtl_tb", tmp_path / "rtl",
                        with_lib=False, extra=["--assert", "+define+ASSERT_ON"])
    got = [(int(l.split()[3], 16), int(l.split()[4])) for l in out if l.startswith("O rsp ")]
    assert [v for v, _ in got] == stream_ref(cmds)
    return design, got


def test_plan_resolves_memory_paths():
    from fw.hdl import storage
    from fw.hdl.spl_flow import partition
    p = partition(FILES, "mm_top", ["mm_rw"])
    rep = storage.plan(p.shell, {"u.mem": {"bind": "sram", "macro": "mm_ram_shim"}})
    row = next(r for r in rep["rows"] if r["path"] == "u.mem")
    assert row["kind"] == "memory" and row["module"] == "mm_ram_shim"
    assert (row["depth"], row["bits"], row["flop_bits"], row["ram_bits"]) == (16, 16, 0, 256)
    assert "u.mem" in storage.format_report(rep)
    for knob, msg in [({"u.mem": {"bind": "xls_fifo"}}, "may be bound to"),
                      ({"u.mem": {"bind": "wrapper"}}, "needs `module:`"),
                      ({"u.mem": {"read_latency": 2}}, "1-cycle read"),
                      ({"u.nope": {"bind": "flops"}}, "its memories")]:
        p = partition(FILES, "mm_top", ["mm_rw"])
        with pytest.raises(XlsFlowError, match=msg):
            storage.plan(p.shell, knob)


@needs_xls
@needs_sim
@pytest.mark.verilator
def test_design_same_stream_any_binding(tmp_path):
    d, base = _design(tmp_path / "flops", None)
    assert "fw_ram_1rw_model" in d.files["mm_top.sv"]
    for name, knob, module in [
            ("sram", {"u.mem": {"bind": "sram", "macro": "mm_ram_shim"}}, "mm_ram_shim"),
            ("wrapper", {"u.mem": {"bind": "wrapper", "module": "mm_ram_shim"}}, "mm_ram_shim")]:
        d, got = _design(tmp_path / name, knob)
        assert module in d.files["mm_top.sv"], name
        assert got == base, name


DFM = REPO / "packages" / "python" / "bin" / "dfm"
FLOW = """\
package:
  name: mm
  imports: [fw.hdl.spl, fw.hdl.knobs, synth.xls, zuspec.xls]
  with:
    kset: {type: str, value: k}
  tasks:
  - name: knob-file
    uses: std.FileSet
    with: {type: fwKnobFile, base: knobs, include: ["${{ kset }}.yaml"]}
  - name: knobs
    uses: fw.hdl.knobs.Resolve
    needs: [knob-file]
  - name: src
    uses: std.FileSet
    needs: [knobs]
    with: {type: systemVerilogSource, base: src, include: ["mem_pkg.sv"]}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src, knobs]
    with: {top: mm_top, xls: [mm_rw]}
  - name: rtl
    uses: synth.xls.Codegen
    needs: [part, knobs]
  - name: sig
    uses: zuspec.xls.Signature
    needs: [part, rtl]
  - name: top
    uses: fw.hdl.spl.Integrate
    needs: [part, sig, knobs]
  - name: all
    needs: [top]
"""
KNOBS = """\
design: {top: mm_top, xls: [mm_rw]}
xls:
  default: {pipeline_stages: 2, delay_model: unit}
"""


@needs_xls
@needs_sim
@pytest.mark.verilator
@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_dfm_two_stages_flops_and_sram(tmp_path):
    """Through dfm at 2 stages: the memory's codegen flags reach codegen
    (the RAM timing is kept), and flops and an SRAM shim give one stream."""
    import json
    import os
    import shutil
    import subprocess
    import zuspec.ir.core as ir
    cmds = [c for _, c in schedule(5)["cmd"]]
    streams = {}
    for bind in ("flops", "sram"):
        d = tmp_path / bind
        (d / "knobs").mkdir(parents=True)
        (d / "src").mkdir()
        shutil.copy(PKG, d / "src")
        shutil.copy(SHIM, d / "src")
        (d / "flow.yaml").write_text(FLOW)
        (d / "knobs" / "k.yaml").write_text(KNOBS + (
            "storage:\n  u.mem: {bind: sram, macro: mm_ram_shim, files: [../src/mm_ram_shim.sv]}\n"
            if bind == "sram" else ""))
        r = subprocess.run([str(DFM), "run", "all"], cwd=d, capture_output=True, text=True,
                           env=dict(os.environ))
        assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
        rd = d / "rundir"
        cg = json.loads((rd / "mm.part" / "partition.codegen.json").read_text())
        args = " ".join(a for m in cg["modules"].values() for a in m.get("args", []))
        assert "mem_rd:recv:mem_req:send:0:0" in args
        assert "--flop_single_value_channels=false" in args
        rep = json.loads((rd / "mm.part" / "storage.json").read_text())
        (row,) = [x for x in rep["rows"] if x["path"] == "u.mem"]
        assert row["bind"] == bind
        rtl = sorted({Path(p) for p in (rd / "mm.top").rglob("*.sv")} |
                     {Path(p) for p in (rd / "mm.rtl").rglob("*.sv")})
        (sig_path,) = [p for p in (rd / "mm.top").rglob("*.json")
                       if json.loads(p.read_text()).get("format") == "zuspec.block-signature"]
        sig = ir.load_signature(str(sig_path))
        tb = tmp_path / f"{bind}_tb.sv"
        tb.write_text(rtl_testbench(sig, {"cmd": cmds}, seed=3, throttle=1, cycles=True))
        lib = RAM_LIB + ([SHIM] if bind == "sram" else [])
        out = run_verilator(rtl + lib + [tb], "xh_rtl_tb", tmp_path / f"{bind}_rtl",
                            with_lib=False, extra=["--assert", "+define+ASSERT_ON"])
        streams[bind] = [(int(l.split()[3], 16), int(l.split()[4]))
                         for l in out if l.startswith("O rsp ")]
        assert [v for v, _ in streams[bind]] == stream_ref(cmds) != []
    assert streams["sram"] == streams["flops"]
