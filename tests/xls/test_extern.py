"""Wrapped IP: a Verilog module behind a class (src/fw_extern.svh,
fw.hdl.extern). The wrapper's extern_map() is run by the elaborator, checked
against the module's header with its parameter values applied, and turned into
the block signature Integrate wires it by; nobody writes a signature.

ext_top #(N) chains N wrapped fw_rv_fifo instances (each depth computed from its
parameter object) and an XLS child; arb_top feeds three wrapped FIFOs into
fw_arbiter realized by a supplied module with other pin names and an
active-low reset. The class model and the RTL agree.
"""
import json
import random
import subprocess
from pathlib import Path
from fw_tools import tool

import pytest

from fw.hdl.errors import FwHdlError
from fw.hdl.verif.canon import Event, Rule, check, compare
from fw.hdl.xls_flow import sv_to_structure
from xls_harness import REPO, VERILATOR, proc_testbench, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
EXT = HERE / "extern"
FILES = [str(HERE / "compose" / "hier_pkg.sv"), str(EXT / "ext_pkg.sv")]
BAD = FILES + [str(EXT / "ext_bad_pkg.sv")]
FIFO = REPO / "src" / "rtl" / "fw_rv_fifo.sv"
ARB = REPO / "tests" / "stdlib" / "cosim" / "ref_arb3.sv"
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")


def part(top, files=FILES, xls=("add_k",), **kw):
    from fw.hdl.spl_flow import partition
    return partition(files, top, list(xls), **kw)


def rtl(tmp_path, top, xls=("add_k",)):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, top, list(xls))
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    return design, paths


# --------------------------------------------------------------- structure

def test_one_record_per_specialization():
    sh = part("ext_top3_t").shell
    q = [c for c in sh.children if c["name"].startswith("q_")]
    assert [(c["engine"], c["realization"], c["module"]) for c in q] == \
        [("extern", "wrapped", "fw_rv_fifo")] * 3
    # depth 1, 2, 3 -> DEPTH 1, 2, 4 (computed in extern_map); three signatures
    assert [c["extern"]["params"] for c in q] == \
        [{"WIDTH": "8", "DEPTH": d} for d in ("1", "2", "4")]
    assert len({c["sig"] for c in q}) == 3
    assert {c["name"]: c["engine"] for c in sh.children}["x"] == "xls"


def test_same_specialization_shares_one_record():
    sh = part("arb_top", xls=()).shell
    q = [c for c in sh.children if c["name"].startswith("q_")]
    assert len({c["sig"] for c in q}) == 1


def test_derived_signature_matches_the_pins():
    from fw.hdl.spl_flow import extern_signatures
    import zuspec.ir.core as ir
    sh = part("ext_top1_t").shell
    q0 = next(c for c in sh.children if c["name"] == "q_0")
    sig = extern_signatures(sh)[q0["sig"]]
    assert (sig.name, sig.clock, sig.reset, sig.reset_active_low) == \
        ("fw_rv_fifo", "clk", "rst", False)
    ch = {c.name: (c.direction, c.flow_control, c.ports, c.payload.bits) for c in sig.channels}
    assert ch == {"in": ("in", "ready_valid",
                         {"data": "in_data", "valid": "in_vld", "ready": "in_rdy"}, 8),
                  "out": ("out", "ready_valid",           # the xls style plus a data override
                          {"data": "out_data", "valid": "out_vld", "ready": "out_rdy"}, 8)}
    assert sig.sources == [str(FIFO)]
    # the record is in partition.json, as written
    rec = q0["extern"]["record"]
    assert rec["format"] == "fw-hdl.extern-record" and rec["module"] == "fw_rv_fifo"
    json.dumps(sh.to_json())


def test_supplied_module_with_other_names():
    from fw.hdl.spl_flow import extern_signatures
    sh = part("arb_top", xls=()).shell
    arb = next(c for c in sh.children if c["name"] == "arb")
    sig = extern_signatures(sh)[arb["sig"]]
    assert (sig.clock, sig.reset, sig.reset_active_low) == ("clk_i", "rst_ni", True)
    assert sig.channel("in_1").ports == {"data": "req1_data", "valid": "req1_valid",
                                         "ready": "req1_ready"}
    assert sig.channel("out").payload.bits == 10


# --------------------------------------------------------------- negatives

@pytest.mark.parametrize("top, msg, line", [
    ("bad_no_reset_t", r"pin\(s\) \['rst'\] of fw_rv_fifo are not accounted for", "extern_map"),
    ("bad_unknown_pin_t", r"tie: fw_rv_fifo has no pin 'nope'", "x.tie(\"nope\""),
    ("bad_twice_t", r"pin 'clk' of fw_rv_fifo is both the clock and a tie", "x.tie(\"clk\""),
    ("bad_width_t", r"port in data: pin 'in_data' of fw_rv_fifo is 9 bits with parameters "
                    r"WIDTH=9, DEPTH=1, expected 8", "x.rv(in"),
    ("bad_dir_t", r"port in ready: pin 'out_rdy' of fw_rv_fifo is an input, expected an output",
     "x.rv(in"),
    ("bad_unmapped_t", r"does not map port\(s\) \['out'\]", "extern_map"),
    ("bad_param_t", r"no parameter NOPE", "extern_map"),
    ("bad_kind_t", r"port in is a ready/valid port; map it with x.rv", "x.level(in"),
    ("bad_per_instance_t", r"a map may depend only on the class and its parameter object",
     "extern_map"),
])
def test_map_errors_point_at_the_line(top, msg, line):
    with pytest.raises(FwHdlError, match=msg) as ei:
        part(top, files=BAD, xls=())
    d = ei.value.diagnostic
    assert d.file.endswith("ext_bad_pkg.sv")
    text = Path(d.file).read_text().splitlines()[d.line - 1]
    assert line in text, (d.line, text)


def test_knob_and_wrapper_together_rejected():
    ext = {"ext_q_rtl": {"signature": "x.json", "module": "fw_rv_fifo", "files": []}}
    with pytest.raises(FwHdlError, match="also assigned by knob design.extern"):
        part("ext_top1_t", extern=ext)


def test_fileset_by_name(tmp_path):
    """extern_fileset() may name a fileset (knob design.filesets)."""
    sh = part("named_fs_t", files=BAD, xls=(), filesets={"fifo": [str(FIFO)]}).shell
    assert sh.children[0]["extern"]["files"] == [str(FIFO)]
    with pytest.raises(FwHdlError, match="no file .*fifo"):
        part("named_fs_t", files=BAD, xls=())


# --------------------------------------------------------------- RTL

def ref(x):
    return (x + 3) & 0xff


def trace(want, outs):
    ev = [Event("in", "in", i, i, data=w) for i, w in enumerate(want)]
    return ev + [Event("out", "out", len(want) + j, j, data=v) for j, v in enumerate(outs)]


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("top", ["ext_top1_t", "ext_top3_t"])
def test_model_and_rtl_agree(tmp_path, top):
    design, paths = rtl(tmp_path, top)
    xs = [r.randrange(256) for r in [random.Random(top)] for _ in range(150)]
    want = [ref(x) for x in xs]
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, {"in": xs}, 5))
    out = run_verilator(paths + [FIFO, tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False)
    got = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    comp = sv_to_structure(FILES, top).component
    mtb = tmp_path / "xh_proc_tb.sv"
    mtb.write_text(proc_testbench(["hier_pkg", "ext_pkg"], top, comp, {"in": xs}))
    mout = run_verilator(FILES + [mtb], "xh_proc_tb", tmp_path / "model")
    model = [int(l.split()[3], 16) for l in mout if l.startswith("O out ")]
    assert check(trace(want, got), Rule()) == []
    assert compare(trace(want, model), trace(want, got), Rule(), names=("model", "rtl")) == []


def by_input(outs):
    per = {0: [], 1: [], 2: []}
    for v in outs:
        per[v >> 8].append(v & 0xff)
    return per


@pytest.mark.verilator
def test_arbiter_model_and_rtl_agree(tmp_path):
    """Each input's values come out in order, each once, in both views
    (the grant order between inputs may differ)."""
    design, paths = rtl(tmp_path, "arb_top", xls=())
    r = random.Random(3)
    ins = {n: [r.randrange(256) for _ in range(60)] for n in ("a", "b", "c")}
    want = {i: ins[n] for i, n in enumerate(("a", "b", "c"))}
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, ins, 7))
    out = run_verilator(paths + [FIFO, ARB, tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False)
    got = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    assert by_input(got) == want
    comp = sv_to_structure(FILES, "arb_top").component
    mtb = tmp_path / "xh_proc_tb.sv"
    mtb.write_text(proc_testbench(["hier_pkg", "ext_pkg"], "arb_top", comp, ins, clocked=True))
    mout = run_verilator(FILES + [mtb], "xh_proc_tb", tmp_path / "model")
    model = [int(l.split()[3], 16) for l in mout if l.startswith("O out ")]
    assert by_input(model) == want


@needs_xls
@pytest.mark.verilator
def test_integrated_top_lint_clean(tmp_path):
    design, paths = rtl(tmp_path, "ext_top3_t")
    r = subprocess.run([str(VERILATOR), "--lint-only", "-Wall", "--top-module", design.top,
                        *map(str, paths), str(FIFO)], capture_output=True, text=True,
                       cwd=tmp_path)
    bad = [l for l in r.stderr.splitlines() if ("%Warning" in l or l.startswith("%Error"))
           and f"{design.top}.sv" in l]
    assert bad == [], r.stderr[-3000:]


@pytest.mark.verilator
def test_active_low_reset_and_ties(tmp_path):
    """The instance gets its parameters, `!rst` on an active-low reset, ties
    and open outputs."""
    design, _ = rtl(tmp_path, "arb_top", xls=())
    top = design.files["arb_top.sv"]
    assert "ref_arb3 #(.LOCK(1)) arb (" in top
    assert ".rst_ni(!rst)" in top
    from fw.hdl.spl_flow import spl_to_rtl
    d = spl_to_rtl(BAD, "tie_open_t", [])
    t = d.files["tie_open_t.sv"]
    assert ".dbg_en(1'd0)" in t and ".dbg_q()" in t and ".mode(2'd2)" in t


@pytest.mark.verilator
def test_map_records_in_simulation(tmp_path):
    out = run_verilator(FILES + [EXT / "map_tb.sv"], "map_tb", tmp_path)
    assert "module=fw_rv_fifo fileset=../../../src/rtl/fw_rv_fifo.sv" in out
    assert "param WIDTH=8" in out and "param DEPTH=4" in out
    assert "clock=clk reset=rst low=0" in out
    assert "bind rv in in style=fw data=in_data" in out
    assert "bind rv out out style=xls data=out_data" in out


DFM = tool("dfm")


@needs_xls
@pytest.mark.verilator
@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_through_dfm_tasks(tmp_path):
    """Partition -> Codegen -> Signature -> Integrate with wrapped children,
    one of them finding its module through a knob fileset; the outputs
    simulate and match the reference."""
    import os
    knobs = tmp_path / "knobs.yaml"
    knobs.write_text(
        "design:\n  top: mix_t\n  xls: [add_k]\n"
        f"  filesets:\n    fifo: [{FIFO}]\n"
        "xls:\n  default: {pipeline_stages: 1, delay_model: unit}\n")
    (tmp_path / "flow.yaml").write_text(f"""\
package:
  name: ext
  imports: [fw.hdl.spl, fw.hdl.knobs, synth.xls, zuspec.xls]
  tasks:
  - name: knob-file
    uses: std.FileSet
    with: {{type: fwKnobFile, include: [knobs.yaml]}}
  - name: knobs
    uses: fw.hdl.knobs.Resolve
    needs: [knob-file]
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {EXT.parent},
            include: [compose/hier_pkg.sv, extern/ext_pkg.sv, extern/ext_bad_pkg.sv]}}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src, knobs]
    with: {{top: mix_t, xls: [add_k]}}
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
    import zuspec.ir.core as ir
    rundir = tmp_path / "rundir"
    top = (rundir / "ext.top" / "mix_t.sv").read_text()
    assert "fw_rv_fifo u (" in top                          # default parameters
    assert "fw_rv_fifo #(.WIDTH(8), .DEPTH(2)) w (" in top
    sig = ir.load_signature(rundir / "ext.top" / "mix_t.sig.json")
    xs = [r.randrange(256) for r in [random.Random(5)] for _ in range(80)]
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(sig, {"in": xs}, 4))
    srcs = sorted(rundir.glob("ext.rtl/**/*.sv")) + [rundir / "ext.top" / "mix_t.sv"]
    out = run_verilator([FIFO, *srcs, tb], "xh_rtl_tb", tmp_path / "sim", with_lib=False)
    assert [int(l.split()[3], 16) for l in out if l.startswith("O out ")] == [ref(x) for x in xs]
