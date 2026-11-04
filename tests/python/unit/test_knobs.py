"""Knob files -- merge, origins, schema, codegen flags, SV package."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "xls"))

from fw.hdl.knobs import KnobError, load

REPO = Path(__file__).resolve().parents[3]


def write(tmp, name, text):
    p = tmp / name
    p.write_text(text)
    return p


COMMON = """\
design:
  top: rt_top
  xls: [rt_table, rt_pool]
rtl:
  RT_TAGS: 64
  RT_SAFE: true
xls:
  default: {pipeline_stages: 1, clock_period_ps: 1000, delay_model: unit, flop_inputs: true}
  blocks:
    rt_table: {pipeline_stages: 2}
storage:
  default: {bind: flops}
island:
  exceptions:
    - {channel: rt_table.cfg, kind: single_value, reason: quasi-static config}
"""


def test_base_merge_and_override(tmp_path):
    write(tmp_path, "common.yaml", COMMON)
    k2 = write(tmp_path, "k2.yaml", """\
base: common.yaml
rtl: {RT_TAGS: 32, RT_NAME: fast}
xls:
  blocks:
    rt_pool: {clock_period_ps: 800, flop_outputs_kind: zerolatency}
island:
  exceptions: []
""")
    k = load(k2)
    assert k.top == "rt_top"
    assert k.rtl_params() == {"RT_TAGS": 32, "RT_SAFE": True, "RT_NAME": "fast"}
    assert k.block_options("rt_table") == {"pipeline_stages": 2, "clock_period_ps": 1000,
                                           "delay_model": "unit", "flop_inputs": True}
    assert k.block_options("rt_pool")["clock_period_ps"] == 800
    assert k.exceptions() == []                      # a list replaces, it does not append
    assert [Path(f).name for f in k.files] == ["common.yaml", "k2.yaml"]
    assert k.origin("rtl", "RT_TAGS").file.endswith("k2.yaml")
    assert k.origin("rtl", "RT_SAFE").file.endswith("common.yaml")
    assert k.origin("xls", "blocks", "rt_table", "pipeline_stages").line == 10


def test_codegen_args_and_delay_scale(tmp_path):
    p = write(tmp_path, "k.yaml", COMMON + "delay: {scale: 2.5}\n")
    k = load(p)
    assert k.codegen_args("rt_table") == [
        "--pipeline_stages=2", "--clock_period_ps=2500", "--delay_model=unit",
        "--flop_inputs=true"]


def test_unknown_key_names_its_line(tmp_path):
    p = write(tmp_path, "k.yaml", "xls:\n  default:\n    pipline_stages: 2\n")
    with pytest.raises(KnobError) as e:
        load(p)
    assert f"{p}:3" in str(e.value) or f"{p}:2" in str(e.value)
    assert "pipline_stages" in str(e.value)


def test_bad_value_in_a_base_names_the_base(tmp_path):
    write(tmp_path, "common.yaml", "storage:\n  rt_store.mem: {bind: dram}\n")
    p = write(tmp_path, "k.yaml", "base: [common.yaml]\n")
    with pytest.raises(KnobError) as e:
        load(p)
    assert "common.yaml:2" in str(e.value) and "dram" in str(e.value)


def test_base_cycle(tmp_path):
    write(tmp_path, "a.yaml", "base: b.yaml\n")
    write(tmp_path, "b.yaml", "base: a.yaml\n")
    with pytest.raises(KnobError, match="cycle"):
        load(tmp_path / "a.yaml")


def test_exception_needs_a_reason(tmp_path):
    p = write(tmp_path, "k.yaml",
              "island:\n  exceptions:\n    - {channel: a.b, kind: cdc}\n")
    with pytest.raises(KnobError, match="reason"):
        load(p)


def test_group_with_mixed_schedules_is_rejected(tmp_path):
    p = write(tmp_path, "k.yaml", COMMON + "  groups: {core: [rt_table, rt_pool]}\n")
    with pytest.raises(KnobError, match="one schedule per multi-proc package"):
        load(p)


def test_block_not_in_design(tmp_path):
    p = write(tmp_path, "k.yaml", COMMON.replace("rt_table: {pipeline_stages: 2}",
                                                 "rt_tabel: {pipeline_stages: 2}"))
    with pytest.raises(KnobError, match="rt_tabel: not in design.xls"):
        load(p)


def test_storage_default(tmp_path):
    k = load(write(tmp_path, "k2.yaml", COMMON.replace(
        "  default: {bind: flops}", "  default: {bind: flops}\n  rt_store.mem: "
        "{bind: sram, macro: sp_256x64, read_latency: 1}")))
    assert k.storage("rt_store.mem") == {"bind": "sram", "macro": "sp_256x64", "read_latency": 1}
    assert k.storage("other") == {"bind": "flops"}


def test_storage_section_resolves_files(tmp_path):
    k = load(write(tmp_path, "k3.yaml", COMMON.replace(
        "  default: {bind: flops}", "  default: {bind: flops}\n  q: "
        "{bind: wrapper, module: my_fifo, files: [rtl/my_fifo.sv]}")))
    s = k.storage_section()
    assert s["q"]["files"] == [str((tmp_path / "rtl" / "my_fifo.sv").resolve())]
    assert s["default"] == {"bind": "flops"}


def test_sv_package_compiles(tmp_path):
    from xls_harness import have_verilator, run_verilator  # tests/xls on sys.path below
    k = load(write(tmp_path, "k.yaml", COMMON))
    files = k.write(tmp_path / "out")
    data = json.loads(Path(files["json"]).read_text())
    assert data["format"] == "fw-hdl.knobs" and data["knobs"]["rtl"]["RT_TAGS"] == 64
    sv = Path(files["sv"]).read_text()
    assert "localparam int RT_TAGS = 64;" in sv and "localparam bit RT_SAFE = 1'b1;" in sv
    if not have_verilator():
        pytest.skip("needs verilator")
    tb = tmp_path / "tb.sv"
    tb.write_text("module tb; import rt_top_knobs_pkg::*; initial begin "
                  "if (RT_TAGS != 64 || !RT_SAFE) $fatal(1); $display(\"X done\"); $finish; "
                  "end endmodule\n")
    run_verilator([files["sv"], tb], "tb", tmp_path / "sim", with_lib=False)


def test_cli(tmp_path):
    p = write(tmp_path, "k.yaml", COMMON)
    r = subprocess.run([sys.executable, "-m", "fw.hdl", "knobs", "codegen", str(p), "rt_table"],
                       capture_output=True, text=True, cwd=REPO / "python")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["--pipeline_stages=2", "--clock_period_ps=1000",
                                "--delay_model=unit", "--flop_inputs=true"]
    r = subprocess.run([sys.executable, "-m", "fw.hdl", "knobs", "resolve",
                        str(write(tmp_path, "bad.yaml", "xls: 3\n"))],
                       capture_output=True, text=True, cwd=REPO / "python")
    assert r.returncode == 1 and "bad.yaml:1" in r.stderr


DFM = REPO / "packages" / "python" / "bin" / "dfm"


@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
def test_dfm_resolve(tmp_path):
    write(tmp_path, "common.yaml", COMMON)
    write(tmp_path, "k1.yaml", "base: common.yaml\nrtl: {RT_TAGS: 16}\n")
    write(tmp_path, "bad.yaml", "base: common.yaml\nxls: {blocks: {rt_table: {stages: 2}}}\n")
    write(tmp_path, "flow.yaml", """\
package:
  name: kn
  imports: [fw.hdl.knobs]
  tasks:
  - {name: k1-file, uses: std.FileSet, with: {type: fwKnobFile, include: [k1.yaml]}}
  - {name: k1, uses: fw.hdl.knobs.Resolve, needs: [k1-file]}
  - {name: bad-file, uses: std.FileSet, with: {type: fwKnobFile, include: [bad.yaml]}}
  - {name: bad, uses: fw.hdl.knobs.Resolve, needs: [bad-file]}
""")
    r = subprocess.run([str(DFM), "run", "k1"], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    js = list((tmp_path / "rundir").rglob("rt_top.knobs.json"))
    assert js, list((tmp_path / "rundir").rglob("*"))
    j = js[0]
    assert json.loads(j.read_text())["knobs"]["rtl"]["RT_TAGS"] == 16
    assert list((tmp_path / "rundir").rglob("rt_top_knobs_pkg.sv"))
    r = subprocess.run([str(DFM), "run", "bad"], cwd=tmp_path, capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert r.returncode != 0 and "stages" in out and "Task threw exception" not in out, out[-2000:]


def test_codegen_options_document(tmp_path):
    k = load(write(tmp_path, "k.yaml", COMMON.replace(
        "    rt_table: {pipeline_stages: 2}",
        "    rt_table: {pipeline_stages: 2}\n"
        "    rt_pool: {flop_outputs_kind: skid, worst_case_throughput: 2}")))
    doc = k.codegen_options()
    assert doc["format"] == "xls.codegen-options"
    # clock_period_ps given: Codegen takes the period, pipeline_stages rides in args
    assert doc["modules"]["rt_table"] == {
        "delay_model": "unit", "clock_period_ps": 1000,
        "args": ["--pipeline_stages=2", "--flop_inputs=true"]}
    assert doc["modules"]["rt_pool"]["args"] == [
        "--pipeline_stages=1", "--worst_case_throughput=2", "--flop_inputs=true",
        "--flop_outputs_kind=skid"]
