"""Channel kinds. Each kind round-trips class model -> RTL with the same
stream (fw.hdl.verif.canon); a valid-only top output has no ready pin; a
port bound to an end of another kind is rejected at integration.
"""
import json
import random
from pathlib import Path

import pytest

from fw.hdl.verif.canon import Event, Rule, compare
from fw.hdl.xls_flow import sv_to_structure
from xls_harness import REPO, proc_testbench, rtl_testbench, run_verilator
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
COMPOSE = HERE / "compose"
FILES = [str(COMPOSE / "kinds_pkg.sv")]
RTL_LIB = [REPO / "src" / "rtl" / "fw_rv_fifo.sv", REPO / "src" / "rtl" / "fw_valid_check.sv"]
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")
XLS = {"vtop": ["vinc", "vmix"], "ltop": ["lsrc", "lsum"]}


def _rtl(tmp_path, top, inputs, seed=5):
    from fw.hdl.spl_flow import spl_to_rtl
    design = spl_to_rtl(FILES, top, XLS[top])
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, inputs, seed))
    out = run_verilator(paths + RTL_LIB + [tb], "xh_rtl_tb", tmp_path / "rtl", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    return design, [int(l.split()[3], 16) for l in out if l.startswith("O out ")], out


def _model(tmp_path, top, inputs):
    comp = sv_to_structure(FILES, top).component
    tb = tmp_path / "xh_proc_tb.sv"
    tb.write_text(proc_testbench(["kinds_pkg"], top, comp, inputs))
    out = run_verilator(FILES + [tb], "xh_proc_tb", tmp_path / "model")
    return [int(l.split()[3], 16) for l in out if l.startswith("O out ")]


def _trace(want, outs):
    """In events carry the expected value; out events must match it, in order."""
    ev = [Event("in", "in", i, i, data=w) for i, w in enumerate(want)]
    ev += [Event("out", "out", len(want) + j, j, data=v) for j, v in enumerate(outs)]
    return ev


def test_kinds_reach_the_partition():
    from fw.hdl.spl_flow import partition
    v = partition(FILES, "vtop", XLS["vtop"]).shell
    assert {p["name"]: p["kind"] for p in v.ports} == {"in": "ready_valid", "out": "valid"}
    assert {c["name"]: c["kind"] for c in v.channels} == {"v": "valid", "cr": "ready_valid"}
    l = partition(FILES, "ltop", XLS["ltop"]).shell
    assert {c["name"]: c["kind"] for c in l.channels} == {"ch": "ready_valid", "lb": "level"}
    assert {p["name"]: p["kind"] for p in l.ports}["gain"] == "level"


def test_predicted_signature_kinds():
    from zuspec.be.xls.signature import predict_signature
    from fw.hdl.spl_flow import partition
    blocks = partition(FILES, "ltop", XLS["ltop"]).blocks
    sig = predict_signature(blocks["lsum"])
    lb = sig.channel("lb")
    assert (lb.flow_control, lb.ports) == ("none", {"data": "lb"})
    vb = predict_signature(partition(FILES, "vtop", XLS["vtop"]).blocks["vinc"]).channel("out")
    assert vb.flow_control == "valid" and set(vb.ports) == {"data", "valid", "ready"}


@needs_xls
@pytest.mark.verilator
def test_valid_only_round_trip_and_pins(tmp_path):
    xs = [r.randrange(256) for r in [random.Random(11)] for _ in range(150)]
    design, rtl, _ = _rtl(tmp_path, "vtop", {"in": xs})
    top_sv = design.files["vtop.sv"]
    import re
    port = lambda n: re.search(rf"\b(input|output) logic( \[[^]]*\])? {n},?\n", top_sv)  # noqa: E731
    assert port("out_vld") and not port("out_rdy")                # no ready pin
    assert "fw_valid_check" in top_sv
    out = design.signature.channel("out")
    assert out.flow_control == "valid" and set(out.ports) == {"data", "valid"}
    model = _model(tmp_path, "vtop", {"in": xs})
    want = [((x + 1) & 0xff) ^ 0x5a for x in xs]
    assert model == want
    assert compare(_trace(want, model), _trace(want, rtl), Rule(), names=("model", "rtl")) == []


@needs_xls
@pytest.mark.verilator
def test_level_round_trip(tmp_path):
    """Levels carry no order against streams: a reader may see the old value
    until the new one has crossed its registers (XLS registers a single_value
    channel on both sides). The top-level levels are held from reset, but XLS's
    input register still reads 0 in the first cycle; lb is set by s with the
    first item. So only the first few outputs may use a reset value: bias = 0
    (lb = 1) or lb = 0."""
    xs = [r.randrange(256) for r in [random.Random(12)] for _ in range(150)]
    inputs = {"in": xs, "bias": [7], "gain": [3]}
    design, rtl, _ = _rtl(tmp_path, "ltop", inputs)
    sig = design.signature
    assert set(sig.channel("gain").ports) == {"data"} and sig.channel("gain").flow_control == "none"
    assert "lb" in design.files["ltop.sv"] and "fw_rv_fifo" in design.files["ltop.sv"]
    model = _model(tmp_path, "ltop", inputs)
    steady = [(x + 8 + 3) & 0xff for x in xs]
    assert model == steady
    assert len(rtl) == len(xs)
    assert rtl[3:] == steady[3:]
    early = [(v, {steady[i], (xs[i] + 3) & 0xff, (xs[i] + 4) & 0xff}) for i, v in enumerate(rtl[:3])]
    assert all(v in ok for v, ok in early), early


@needs_xls
def test_kind_mismatch_is_rejected(tmp_path):
    """An extern block whose signature calls a stream port a level."""
    from fw.hdl.spl_flow import XlsFlowError, extern_signatures, integrate, partition
    sig = json.loads((COMPOSE / "ext_neg_rtl.sig.json").read_text())
    sig["channels"][0].update(flow_control="none", ports={"data": "in"})
    (tmp_path / "bad.sig.json").write_text(json.dumps(sig))
    files = [str(COMPOSE / "hier_pkg.sv"), str(COMPOSE / "mixed_pkg.sv")]
    part = partition(files, "mixed_top", ["add_k"],
                     extern={"ext_neg": {"signature": str(tmp_path / "bad.sig.json"),
                                         "module": "ext_neg_rtl"}})
    import zuspec.ir.core as ir
    from zuspec.be.xls.signature import predict_signature, CodegenOptions
    from fw.hdl.spl_flow import module_name
    sigs = {module_name(s): predict_signature(c, CodegenOptions(module_name=module_name(s)))
            for s, c in part.blocks.items()}
    sigs.update(extern_signatures(part.shell))
    with pytest.raises(XlsFlowError, match=r"e\.in is a level port \(ext_neg_rtl\) but is bound "
                                           r"to c0\.get_ex, a ready_valid end"):
        integrate(part.shell, sigs)


@pytest.mark.verilator
def test_valid_channel_reports_a_credit_violation(tmp_path):
    tb = tmp_path / "tb.sv"
    tb.write_text("""\
module tb;
  import fw_hdl_pkg::*;
  import fw_std_pkg::*;
  initial begin
    fw_valid_channel #(bit [7:0], 2) v = new("v", null);
    v.put_ex.put(1); v.put_ex.put(2);
    v.put_ex.put(3);
    $display("X done");
    $finish;
  end
endmodule
""")
    out = run_verilator([tb], "tb", tmp_path / "sim", allow_stop=True)
    assert any("credit violation" in l for l in out), "\\n".join(out[-20:])


@pytest.mark.verilator
def test_valid_check_fires_on_overflow(tmp_path):
    tb = tmp_path / "tb.sv"
    tb.write_text("""\
module tb;
  logic clk = 0, rst = 1, vld = 0, rdy = 1;
  fw_valid_check #(.NAME("link")) chk(.*);
  initial begin
    repeat (2) begin #5 clk = 1; #5 clk = 0; end
    rst = 0;
    vld = 1; #5 clk = 1; #5 clk = 0;          // accepted: fine
    rdy = 0; #5 clk = 1; #5 clk = 0;          // offered while full
    $display("X done");
    $finish;
  end
endmodule
""")
    out = run_verilator([REPO / "src" / "rtl" / "fw_valid_check.sv", tb], "tb", tmp_path / "sim",
                        with_lib=False, allow_stop=True, extra=["--assert", "+define+ASSERT_ON"])
    assert any("fw_valid_check link: offered while full" in l for l in out), "\n".join(out[-10:])


DFM = REPO / "packages" / "python" / "bin" / "dfm"


@needs_xls
@pytest.mark.verilator
@pytest.mark.skipif(not DFM.exists(), reason="needs the packet's dfm")
@pytest.mark.parametrize("top", ["vtop", "ltop"])
def test_kinds_through_dfm_tasks(tmp_path, top):
    """Partition -> Codegen -> Signature -> Integrate keeps each kind: the
    level ports' single_value signatures and the valid-only output's missing
    ready survive the task chain, and the result simulates."""
    import os
    import shutil
    import subprocess
    import zuspec.ir.core as ir
    shutil.copy(COMPOSE / "kinds_pkg.sv", tmp_path / "kinds_pkg.sv")
    (tmp_path / "flow.yaml").write_text(f"""\
package:
  name: kinds
  imports: [fw.hdl.spl, synth.xls, zuspec.xls]
  tasks:
  - name: src
    uses: std.FileSet
    with: {{type: systemVerilogSource, include: [kinds_pkg.sv]}}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src]
    with: {{top: {top}, xls: {XLS[top]}}}
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
    data = json.loads((tmp_path / "rundir" / "kinds.top" / "kinds.top.exec_data.json").read_text())
    outs = data["output"]["output"]
    srcs = [Path(fs["basedir"]) / f for fs in outs if fs["filetype"] == "systemVerilogSource"
            for f in fs["files"]]
    (sig_path,) = [Path(fs["basedir"]) / f for fs in outs if fs["filetype"] == "blockSignature"
                   for f in fs["files"]]
    sig = ir.load_signature(str(sig_path))
    if top == "vtop":
        assert set(sig.channel("out").ports) == {"data", "valid"}
        inputs, want = {"in": list(range(40))}, [((x + 1) & 0xff) ^ 0x5a for x in range(40)]
    else:
        assert set(sig.channel("bias").ports) == {"data"}
        inputs, want = {"in": list(range(40)), "bias": [7], "gain": [3]}, \
            [(x + 11) & 0xff for x in range(40)]
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(sig, inputs, 6))
    out = run_verilator(srcs + [tb], "xh_rtl_tb", tmp_path / "sim", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    got = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    assert got[3:] == want[3:] and len(got) == len(want)
