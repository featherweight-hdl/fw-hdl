"""Storage binding (knob ``storage:``, fw.hdl.storage): the same source,
each channel bound to flops, a supplied wrapper, an XLS FIFO or a RAM.

* Between blocks: st_top's 8-deep store ``q`` as flops, a wrapper and an
  SRAM FIFO (also one level down, ``sub.q``). Every build's output stream is
  the same value for value and cycle for cycle under random back-pressure.
* Inside a group: ``q`` as flops, a wrapper with XLS's FIFO ports, and an
  XLS FIFO. Same stream.
* The bindings that cannot be built are errors naming the knob key.
* The storage report counts flop and RAM bits.
* Through dfm, on the reference design: its queue as flops and as an SRAM
  FIFO, both against the class model and the in-order contract.
"""
import json
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from xls_harness import REPO, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
STORE = HERE / "storage"
FILES = [str(STORE / "store_pkg.sv")]
RTL = REPO / "src" / "rtl"
RTL_LIB = [RTL / n for n in ("fw_rv_fifo.sv", "fw_valid_check.sv", "fw_xls_fifo_wrapper.sv",
                             "fw_sram_fifo.sv", "fw_ram_1r1w_model.sv")]
WRAPPERS = [STORE / "st_wrap_fifo.sv", STORE / "st_xls_wrap.sv"]
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")
GROUP = {"g": ["st_add#(1)", "st_add#(2)"]}


def _plan(top, knob, groups=None):
    from fw.hdl import storage
    from fw.hdl.spl_flow import partition
    xls = ["fw_keyed_table"] if top == "st_tbl_top" else ["st_add"]
    p = partition(FILES, top, xls, groups=groups)
    return p, storage.plan(p.shell, knob)


# --- resolution, errors, report ---------------------------------------------
def test_default_is_flops_and_report():
    p, rep = _plan("st_top", None)
    rows = {r["path"]: r for r in rep["rows"]}
    assert {c["name"]: c["storage"] for c in p.shell.channels} == \
        {"q": {"bind": "flops"}, "r": {"bind": "flops"}}
    assert (rows["q"]["flop_bits"], rows["q"]["ram_bits"]) == (80, 0)


def test_sram_report_and_nested_path():
    from fw.hdl import storage
    p, rep = _plan("st_outer", {"sub.q": {"bind": "sram"}})
    rows = {r["path"]: r for r in rep["rows"]}
    assert rows["sub.q"]["bind"] == "sram" and rows["sub.q"]["macro"] == "fw_ram_1r1w_model"
    # two entries of 10 bits in flops; DEPTH - 1 words in the RAM
    assert (rows["sub.q"]["flop_bits"], rows["sub.q"]["ram_bits"]) == (20, 70)
    assert rows["sub.r"]["bind"] == "flops"
    assert "sub.q" in storage.format_report(rep)


def test_table_is_flops_only():
    p, rep = _plan("st_tbl_top", None)
    assert [r["path"] for r in rep["rows"]] == ["tbl"]
    _plan("st_tbl_top", {"tbl": {"bind": "flops"}})
    with pytest.raises(Exception, match=r"storage\.tbl: .* allows \['flops'\] only: it reads "
                                        r"every entry each cycle"):
        _plan("st_tbl_top", {"tbl": {"bind": "sram"}})


@pytest.mark.parametrize("knob,groups,msg", [
    ({"nosuch": {"bind": "flops"}}, None, r"storage\.nosuch: no channel or storage instance"),
    ({"a": {"bind": "flops"}}, None, r"storage\.a: .* is not a storage class"),
    ({"r": {"bind": "sram"}}, None, r"storage\.r: bind: sram needs DEPTH 3 or more"),
    ({"q": {"bind": "sram", "read_latency": 2}}, None, r"storage\.q: read_latency 2"),
    ({"q": {"bind": "wrapper"}}, None, r"storage\.q: bind: wrapper needs `module:`"),
    ({"q": {"bind": "xls_fifo"}}, None, r"storage\.q: bind: xls_fifo .* between blocks"),
    ({"default": {"bind": "sram"}}, None, r"storage\.default: bind: sram needs DEPTH 3"),
    ({"q": {"bind": "sram"}}, GROUP, r"storage\.q: bind: sram is not available inside group"),
])
def test_errors(knob, groups, msg):
    with pytest.raises(Exception, match=msg):
        _plan("st_top", knob, groups)


def test_group_takes_one_form():
    # q is inside the group; give the group a second internal channel by
    # grouping all three stages, then bind the two differently.
    groups = {"g": ["st_add#(1)", "st_add#(2)", "st_add#(4)"]}
    _plan("st_top", {"q": {"bind": "xls_fifo"}, "r": {"bind": "xls_fifo"}}, groups)
    with pytest.raises(Exception, match=r"group 'g' .* one FIFO form; they differ"):
        _plan("st_top", {"q": {"bind": "xls_fifo"}}, groups)


def test_group_flags():
    from fw.hdl import storage
    for knob, flag in [(None, "--fifo_module=fw_xls_fifo_wrapper"),
                       ({"q": {"bind": "xls_fifo"}}, "--materialize_internal_fifos"),
                       ({"q": {"bind": "wrapper", "module": "st_xls_wrap"}},
                        "--fifo_module=st_xls_wrap")]:
        p, _ = _plan("st_top", knob, GROUP)
        assert storage.group_flags(p.groups["g"]) == ["--multi_proc", flag]


# --- the same stream, whatever the binding ----------------------------------
def _stream(tmp_path, top, storage, groups=None, seed=3):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, top, ["st_add"], groups=groups, storage=storage)
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    rng = random.Random(seed)
    xs = [rng.randrange(1024) for _ in range(300)]
    tb = tmp_path / "xh_rtl_tb.sv"
    # throttle 1: the output is ready about half the time, so q fills
    tb.write_text(rtl_testbench(design.signature, {"in": xs}, seed, throttle=1, cycles=True))
    out = run_verilator(paths + RTL_LIB + WRAPPERS + [tb], "xh_rtl_tb", tmp_path / "rtl",
                        with_lib=False, extra=["--assert", "+define+ASSERT_ON"])
    got = [(int(l.split()[3], 16), int(l.split()[4])) for l in out if l.startswith("O out ")]
    assert [v for v, _ in got] == [(x + 7) & 0x3ff for x in xs]
    return design, got


@needs_xls
@pytest.mark.verilator
def test_between_blocks_same_stream(tmp_path):
    base_d, base = _stream(tmp_path / "flops", "st_top", None)
    assert "fw_rv_fifo" in base_d.files["st_top.sv"]
    for name, knob, module in [
            ("wrapper", {"q": {"bind": "wrapper", "module": "st_wrap_fifo"}}, "st_wrap_fifo"),
            ("sram", {"q": {"bind": "sram"}}, "fw_sram_fifo")]:
        d, got = _stream(tmp_path / name, "st_top", knob)
        assert module in d.files["st_top.sv"], name
        assert got == base, name
    d, got = _stream(tmp_path / "nested", "st_outer", {"sub.q": {"bind": "sram"}})
    assert "fw_sram_fifo" in "".join(d.files.values())
    assert got == base


@needs_xls
@pytest.mark.verilator
def test_inside_group_same_stream(tmp_path):
    _, base = _stream(tmp_path / "flops", "st_top", None)
    for name, knob, needle in [
            ("gflops", None, "fw_xls_fifo_wrapper"),
            ("gwrap", {"q": {"bind": "wrapper", "module": "st_xls_wrap"}}, "st_xls_wrap"),
            ("gxls", {"q": {"bind": "xls_fifo"}}, None)]:
        d, got = _stream(tmp_path / name, "st_top", knob, GROUP)
        if needle:
            assert needle in d.files["g.sv"], name
        else:
            assert "fw_xls_fifo_wrapper" not in d.files["g.sv"]
        assert got == base, name


# --- through dfm, on the reference design (examples/resp_tracker) ------------
DFM = REPO / "packages" / "python" / "bin" / "dfm"
EXAMPLE = REPO / "examples" / "resp_tracker"


def _dfm_build(d, name, text):
    (d / "knobs" / f"{name}.yaml").write_text(text)
    r = subprocess.run([str(DFM), "run", "all", "-D", f"kset={name}"], cwd=d,
                       capture_output=True, text=True, env=dict(os.environ))
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    return d / "rundir"


@needs_xls
@pytest.mark.verilator
@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_reference_design_flops_and_sram(tmp_path):
    """The queue between the two blocks as flops and as an SRAM FIFO (6
    deep): the same RTL stream cycle for cycle, in order, equal to the class
    model; the latency report equals the measured latency on both."""
    import zuspec.ir.core as ir
    from fw.hdl.verif.canon import Rule, check, compare
    from fw.hdl.xls_flow import sv_to_structure
    from test_resp_tracker import LAT_TB, _files, stimulus, trace
    from xls_harness import proc_testbench
    addrs = stimulus(seed=4)
    streams = {}
    for bind in ("flops", "sram"):
        d = tmp_path / bind
        shutil.copytree(EXAMPLE, d, ignore=shutil.ignore_patterns("rundir"))
        rd = _dfm_build(d, f"s_{bind}", "base: k0.yaml\nrtl: {RT_Q_DEPTH: 6}\n"
                        + ("storage:\n  q: {bind: sram}\n" if bind == "sram" else ""))
        part = json.loads((rd / "resp_tracker.part" / "partition.json").read_text())
        assert {c["name"]: c["storage"]["bind"] for c in part["channels"]} == {"q": bind}
        rep = json.loads((rd / "resp_tracker.part" / "storage.json").read_text())
        (row,) = [r for r in rep["rows"] if r["path"] == "q"]
        assert row["ram_bits"] == (5 * row["bits"] if bind == "sram" else 0)
        rtl = _files(rd, "resp_tracker.top", "systemVerilogSource")
        top_sv = next(p for p in rtl if p.name == "rt_top.sv").read_text()
        assert ("fw_sram_fifo" in top_sv) == (bind == "sram")
        (sig_path,) = _files(rd, "resp_tracker.top", "blockSignature")
        sig = ir.load_signature(str(sig_path))
        tb = tmp_path / f"{bind}_tb.sv"
        tb.write_text(rtl_testbench(sig, {"req": addrs}, seed=3, throttle=1, cycles=True))
        out = run_verilator(rtl + [tb], "xh_rtl_tb", tmp_path / f"{bind}_rtl", with_lib=False,
                            extra=["--assert", "+define+ASSERT_ON"])
        streams[bind] = [(int(l.split()[3], 16), int(l.split()[4]))
                         for l in out if l.startswith("O rsp ")]
        outs = [v for v, _ in streams[bind]]
        assert check(trace(addrs, outs), Rule()) == []
        pkg = _files(rd, "resp_tracker.knobs", "systemVerilogSource")
        files = [str(p) for p in pkg] + [str(d / "src" / "rt_pkg.sv")]
        comp = sv_to_structure(files, "rt_top").component
        mtb = tmp_path / f"{bind}_proc_tb.sv"
        mtb.write_text(proc_testbench(["rt_pkg"], "rt_top", comp, {"req": addrs}))
        mout = run_verilator(files + [mtb], "xh_proc_tb", tmp_path / f"{bind}_model")
        model = [int(l.split()[3], 16) for l in mout if l.startswith("O rsp ")]
        assert compare(trace(addrs, model), trace(addrs, outs), Rule(),
                       names=("model", "rtl")) == []
        lat = json.loads((rd / "resp_tracker.latency" / "latency.json").read_text())
        (path,) = [p for p in lat["paths"] if (p["src"], p["dst"]) == ("req", "rsp")]
        ltb = tmp_path / f"{bind}_lat_tb.sv"
        ltb.write_text(LAT_TB)
        lout = run_verilator(rtl + [ltb], "xh_lat_tb", tmp_path / f"{bind}_lat", with_lib=False)
        (measured,) = [int(l.split()[1]) for l in lout if l.startswith("L ")]
        assert path["cycles"] == measured
    assert streams["sram"] == streams["flops"]
