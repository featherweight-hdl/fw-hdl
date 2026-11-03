"""Boundary checks -- one negative per rule, plus the passing forms."""
import types
from pathlib import Path

import pytest

import zuspec.ir.core as ir
from fw.hdl.check.boundary import block_ports, check, yosys

pytestmark = pytest.mark.skipif(yosys() is None, reason="needs yosys")

RTL = """\
// registered: out_vld/out from a flop, in_rdy from state only
module reg_blk(input clk, input rst, input [7:0] in, input in_vld, output in_rdy,
               output [7:0] out, output out_vld, input out_rdy);
  reg full; reg [7:0] q;
  assign in_rdy = !full; assign out_vld = full; assign out = q;
  always @(posedge clk) if (rst) full <= 0; else begin
    if (in_vld && !full) begin full <= 1; q <= in; end
    else if (out_rdy && full) full <= 0;
  end
endmodule
// a wire: everything combinational
module comb_blk(input clk, input rst, input [7:0] in, input in_vld, output in_rdy,
                output [7:0] out, output out_vld, input out_rdy);
  assign out = in + 8'd1; assign out_vld = in_vld; assign in_rdy = out_rdy;
endmodule
// valid waits for ready: illegal
module bad_blk(input clk, input rst, input [7:0] in, input in_vld, output in_rdy,
               output [7:0] out, output out_vld, input out_rdy);
  assign out = in; assign out_vld = in_vld & out_rdy; assign in_rdy = out_rdy;
endmodule
"""


def sig(module):
    s = ir.BlockSignature(name=module, clock="clk", reset="rst")
    for n, d in (("in", "in"), ("out", "out")):
        s.channels.append(ir.ChannelSignature(
            name=n, direction=d, payload=ir.DataTypeInt(bits=8, signed=False),
            ports={"data": n, "valid": f"{n}_vld", "ready": f"{n}_rdy"}))
    return s


@pytest.fixture(scope="module")
def rtl(tmp_path_factory):
    p = tmp_path_factory.mktemp("rtl") / "blocks.v"
    p.write_text(RTL)
    return str(p)


def shell(children, channels, binds):
    """children: {inst: module}; channels: {name: depth};
    binds: [(inst, port, provider, end)]"""
    return types.SimpleNamespace(
        top="t", module="t", ports=[],
        channels=[{"name": n, "bits": 8, "depth": d} for n, d in channels.items()],
        children=[{"name": i, "module": m} for i, m in children.items()],
        binds=[{"port": [i, p], "provider": [n, e]} for i, p, n, e in binds])


def chain(depth):
    return (["a", "b"], {"c0": depth},
            [("a", "out", "c0", "put_ex"), ("b", "in", "c0", "get_ex")])


def run(rtl, mods, chans, binds, **kw):
    blocks = {i: block_ports(sig(m), [rtl]) for i, m in mods.items()}
    return check(shell(mods, chans, binds), blocks, **kw)


def test_deps_from_yosys(rtl):
    bp = block_ports(sig("reg_blk"), [rtl])
    assert bp.deps == {"out": set(), "out_vld": set(), "in_rdy": set()}
    bp = block_ports(sig("comb_blk"), [rtl])
    assert bp.deps == {"out": {"in"}, "out_vld": {"in_vld"}, "in_rdy": {"out_rdy"}}


def test_depth0_between_comb_blocks_is_not_registered(rtl):
    f = run(rtl, {"a": "comb_blk", "b": "comb_blk"}, {"c0": 0},
            [("a", "out", "c0", "put_ex"), ("b", "in", "c0", "get_ex")])
    assert [x.rule for x in f] == ["registered"] and "c0" in f[0].msg


def test_fifo_or_registered_ports_or_exception_pass(rtl):
    binds = [("a", "out", "c0", "put_ex"), ("b", "in", "c0", "get_ex")]
    assert run(rtl, {"a": "comb_blk", "b": "comb_blk"}, {"c0": 1}, binds) == []
    assert run(rtl, {"a": "reg_blk", "b": "reg_blk"}, {"c0": 0}, binds) == []
    assert run(rtl, {"a": "comb_blk", "b": "comb_blk"}, {"c0": 0}, binds,
               exceptions=[{"channel": "c0", "kind": "same_cycle", "reason": "r"}]) == []


def test_comb_cycle(rtl):
    f = run(rtl, {"a": "comb_blk", "b": "comb_blk"}, {"c0": 0, "c1": 0},
            [("a", "out", "c0", "put_ex"), ("b", "in", "c0", "get_ex"),
             ("b", "out", "c1", "put_ex"), ("a", "in", "c1", "get_ex")],
            require_registered=False)
    assert [x.rule for x in f] == ["comb_cycle"]
    # a FIFO anywhere on the loop breaks it
    assert run(rtl, {"a": "comb_blk", "b": "comb_blk"}, {"c0": 0, "c1": 1},
               [("a", "out", "c0", "put_ex"), ("b", "in", "c0", "get_ex"),
                ("b", "out", "c1", "put_ex"), ("a", "in", "c1", "get_ex")],
               require_registered=False) == []


def test_depth0_loopback(rtl):
    f = run(rtl, {"a": "reg_blk"}, {"c": 0},
            [("a", "out", "c", "put_ex"), ("a", "in", "c", "get_ex")])
    assert [x.rule for x in f] == ["loopback"]


def test_valid_on_ready(rtl):
    f = run(rtl, {"a": "bad_blk", "b": "reg_blk"}, {"c0": 1},
            [("a", "out", "c0", "put_ex"), ("b", "in", "c0", "get_ex")])
    assert [x.rule for x in f] == ["valid_on_ready"] and "out_rdy" in f[0].msg


# --- through Integrate (dv-flow) ----------------------------------------------
import os  # noqa: E402
import subprocess  # noqa: E402

from zuspec.be.xls.testing.xlstools import codegen_main, opt_main  # noqa: E402

HERE = Path(__file__).resolve().parent
DFM = HERE.parents[1] / "packages" / "python" / "bin" / "dfm"

INTEGRATE_FLOW = """\
package:
  name: bd
  imports: [fw.hdl.spl, fw.hdl.knobs, synth.xls, zuspec.xls]
  tasks:
  - name: corpus
    uses: std.FileSet
    with: {{type: systemVerilogSource, base: {corpus}, include: [crc32_pkg.sv, rle_pkg.sv, rle8_pkg.sv]}}
  - name: src
    uses: std.FileSet
    needs: [corpus]
    with: {{type: systemVerilogSource, base: {compose}, include: [chain_pkg.sv]}}
  - name: knob-file
    uses: std.FileSet
    with: {{type: fwKnobFile, include: [knobs.yaml]}}
  - {{name: knobs, uses: fw.hdl.knobs.Resolve, needs: [knob-file]}}
  - name: part
    uses: fw.hdl.spl.Partition
    needs: [src]
    with: {{top: chain_top, xls: [rle_enc8_t, pkt_framer, crc32_stream]}}
  - {{name: rtl, uses: synth.xls.Codegen, needs: [part]}}
  - {{name: sig, uses: zuspec.xls.Signature, needs: [part, rtl]}}
  - name: top
    uses: fw.hdl.spl.Integrate
    needs: [part, sig, knobs]
    with: {{registered_boundaries: {sev}}}
"""


@pytest.mark.skipif(not DFM.exists() or codegen_main() is None or opt_main() is None,
                    reason="needs dfm and XLS")
@pytest.mark.parametrize("sev,exception,ok", [("warn", False, True), ("error", False, False),
                                              ("error", True, True)])
def test_integrate_registered_boundaries(tmp_path, sev, exception, ok):
    """chain_top's c0 is depth 0 between two XLS blocks whose ports are not
    registered: a warning by default, an error when asked, waived by a knob
    exception."""
    knobs = "design: {top: chain_top}\n"
    if exception:
        knobs += ("island:\n  exceptions:\n"
                  "    - {channel: c0, kind: merged, reason: rendezvous by design}\n")
    (tmp_path / "knobs.yaml").write_text(knobs)
    (tmp_path / "flow.yaml").write_text(INTEGRATE_FLOW.format(
        corpus=HERE / "corpus", compose=HERE / "compose", sev=sev))
    r = subprocess.run([str(DFM), "run", "top"], cwd=tmp_path, capture_output=True,
                       text=True, env=dict(os.environ))
    out = r.stdout + r.stderr
    assert (r.returncode == 0) == ok, out[-3000:]
    flagged = "boundary registered: channel c0" in out.replace("\n", " ").replace("  ", " ")
    assert flagged == (not exception), out[-3000:]
