"""The static subset's proc forms as SV component classes, run on
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


# --- several ops on one channel, loops, multi-write state, guarded state
F5 = str(HERE / "micro" / "micro_f5_pkg.sv")


def _ir(cls: str) -> str:
    return format_package(sv_to_xls([F5], cls))


def _chan(text: str, name: str) -> str:
    return re.search(rf"chan_interface {name}\(([^)]*)\)", text).group(1)


@pytest.mark.verilator
def test_f5_guarded_double_send(workdir):
    text = _ir("f5_dsend")
    assert "strictness=proven_mutually_exclusive" in _chan(text, "out")
    assert "strictness=proven_mutually_exclusive" in _chan(text, "aux")
    xs = [r.randrange(256) for r in [random.Random(5)] for _ in range(60)]
    r = check_proc([F5], "micro_f5_pkg", "f5_dsend", {"in": xs}, workdir)
    assert r.outputs["out"] == [(x + 1) & 0xff if x & 1 else x ^ 0xff for x in xs]
    aux = {0: lambda x: x, 1: lambda x: (x + 16) & 0xff, 3: lambda x: 0}
    assert r.outputs["aux"] == [aux[(x >> 1) & 3](x) for x in xs if (x >> 1) & 3 != 2]


@pytest.mark.verilator
def test_f5_unrolled_per_vc_loop(workdir):
    text = _ir("f5_vc")
    assert "strictness=proven_mutually_exclusive" in _chan(text, "in")
    rng = random.Random(11)
    sel = [rng.randrange(4) for _ in range(50)]
    xs = [rng.randrange(256) for _ in range(50)]
    r = check_proc([F5], "micro_f5_pkg", "f5_vc", {"sel": sel, "in": xs}, workdir)
    sums, want = [0] * 4, []
    for v, x in zip(sel, xs):
        sums[v] = (sums[v] + x) & 0x3ff
        want.append((v << 10) | sums[v])
    assert r.outputs["out"] == want


def _cam_model(cmds):
    vld, keys, out = [0] * 4, [0] * 4, []
    for c in cmds:
        if c >> 11 & 1:
            vld[c >> 9 & 3] = 0
        if c >> 8 & 1:
            free = [k for k in range(4) if not vld[k]]
            if free:
                vld[free[0]], keys[free[0]] = 1, c & 0xff
            out.append((4 | free[0]) if free else 0)
    return out, vld, keys


@pytest.mark.verilator
def test_f5_cam_install_and_release_in_one_activation(workdir):
    rng = random.Random(3)
    cmds = [(rng.randrange(2) << 11) | (rng.randrange(4) << 9) | (rng.randrange(2) << 8) |
            rng.randrange(256) for _ in range(80)]
    cmds += [(1 << 11) | (2 << 9) | (1 << 8) | 0xab]     # release 2 and reuse it at once
    r = check_proc([F5], "micro_f5_pkg", "f5_cam", {"in": cmds}, workdir)
    out, vld, _ = _cam_model(cmds)
    assert r.outputs["out"] == out
    assert r.state["vld"] == sum(b << k for k, b in enumerate(vld))


@pytest.mark.verilator
def test_f5_multi_lane_push(workdir):
    rng = random.Random(9)
    cmds = [(rng.randrange(4) << 24) | rng.getrandbits(24) for _ in range(60)]
    r = check_proc([F5], "micro_f5_pkg", "f5_push", {"in": cmds}, workdir)
    q, wp, want = [0] * 8, 0, []
    for c in cmds:
        for lane in range(min(3, c >> 24)):
            q[wp], wp = (c >> 8 * lane) & 0xff, (wp + 1) & 7
        want.append(q[(wp - 1) & 7])
    assert r.outputs["out"] == want and r.state["wp"] == wp


@pytest.mark.verilator
def test_f5_state_used_only_under_a_guard(workdir):
    text = _ir("f5_gstate")
    assert re.search(r"state_read\(state_element=acc, predicate=", text), text
    assert re.search(r"next_value\(state_element=acc, value=\S+, predicate=", text), text
    xs = [r.randrange(256) for r in [random.Random(4)] for _ in range(60)]
    r = check_proc([F5], "micro_f5_pkg", "f5_gstate", {"in": xs}, workdir)
    acc, want = 100, []
    for x in xs:
        if x & 1:
            acc = (acc + x) & 0xffff
            want.append(acc)
    assert r.outputs["out"] == want


@pytest.mark.verilator
def test_f5_runtime_exclusive_holds(workdir):
    assert "strictness=runtime_mutually_exclusive" in _chan(_ir("f5_rt"), "out")
    xs = [r.randrange(256) & ~3 | r.choice([0, 1, 2]) for r in [random.Random(6)]
          for _ in range(60)]
    r = check_proc([F5], "micro_f5_pkg", "f5_rt", {"in": xs}, workdir)
    assert r.outputs["out"] == [x if x & 1 else x + 1 for x in xs if x & 3]


@pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                    reason="needs opt_main and codegen_main")
@pytest.mark.verilator
def test_f5_runtime_exclusive_both_firing_asserts(workdir):
    """Both guards hold: the class model sends twice, the hardware cannot.
    The interpreter and XLS's RTL both stop at the exclusivity assertion,
    after the same outputs."""
    from xls_harness import check_proc_rtl, xls_roundtrip
    from zuspec.be.xls.lower_proc import lower_component
    from zuspec.be.xls.testing.interp import run_proc
    from fw.hdl.xls_flow import sv_to_component
    comp = sv_to_component([F5], "f5_rt")
    pkg = lower_component(comp)
    xs = [0x10, 0x21, 0x32, 0x43, 0x50]
    r = run_proc(xls_roundtrip(pkg), pkg.top, {"in": xs})
    assert r.stop == "assert" and "active operations on channel out" in str(r.assertion)
    # 0x43 fires both: the first send is out before the assertion stops the run
    assert r.outputs["out"] == [0x21, 0x33, 0x43]
    check_proc_rtl(format_package(pkg), comp, "f5_rt", {"in": xs}, {"out": [0x21, 0x33]},
                   workdir,
                   expect_assert="active operations on channel out")


@pytest.mark.parametrize("cls,msg", [
    ("f5_bad_gap", "can both run in one activation, and another effect lies between them"),
    ("f5_bad_bare", "one of them is unguarded"),
])
def test_f5_rejections(cls, msg):
    from zuspec.be.xls.width import StaticSubsetError
    with pytest.raises(StaticSubsetError) as e:
        sv_to_xls([F5], cls)
    assert msg in str(e.value) and "micro_f5_pkg.sv:" in str(e.value), str(e.value)
