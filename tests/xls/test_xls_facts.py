"""RQ-T0: the XLS facts the library and flow rely on, checked on the packet's
xlsynth. Each test asserts what this version does and records it in
build/xls-facts.json (summarized by hand in docs/research/xls-facts.md).

A failing test here means the toolchain changed under a design decision:
update the decision, not the assertion.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

from zuspec.be.xls.testing.xlstools import codegen_main, find_tool, opt_main

REPO = Path(__file__).resolve().parents[2]
FACTS = REPO / "build" / "xls-facts.json"

needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")


def _version() -> str:
    m = REPO / "packages" / "xlsynth" / "manifest.json"
    try:
        return json.loads(m.read_text())["release"]["version"]
    except (OSError, KeyError, ValueError):
        return "unknown"


def record(fact: str, result, note: str = ""):
    FACTS.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(FACTS.read_text()) if FACTS.exists() else {}
    data.setdefault(_version(), {})[fact] = {"result": result, "note": note}
    FACTS.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _ci(name, direction, strictness="proven_mutually_exclusive", fc="ready_valid"):
    return (f"  chan_interface {name}(direction={direction}, kind=streaming, "
            f"strictness={strictness}, flow_control={fc}, flop_kind=none)")


def _proc(body: str, state="s: (), init={()}", out_strictness="proven_mutually_exclusive",
          out_fc="ready_valid") -> str:
    return (f"package p\n\ntop proc p<a: bits[8] in, o: bits[8] out>({state}) {{\n"
            f"{_ci('a', 'receive')}\n{_ci('o', 'send', out_strictness, out_fc)}\n"
            "  t: token = after_all(id=2)\n"
            "  r: (token, bits[8]) = receive(t, channel=a, id=3)\n"
            "  rt: token = tuple_index(r, index=0, id=4)\n"
            "  d: bits[8] = tuple_index(r, index=1, id=5)\n"
            f"{body}}}\n")


_UNIT_STATE = ("  s: () = state_read(state_element=s, id=1)\n"
               "  nv: () = next_value(state_element=s, value=s, id=9)\n")


def opt_and_codegen(tmp: Path, text: str, *flags, stages: int = 1):
    """(opt ok, codegen ok, message, verilog text)."""
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "p.ir").write_text(text)
    r = subprocess.run([opt_main(), str(tmp / "p.ir")], capture_output=True, text=True)
    if r.returncode != 0:
        return False, False, _err(r.stderr), ""
    (tmp / "p.opt.ir").write_text(r.stdout)
    sv = tmp / "p.sv"
    r = subprocess.run([codegen_main(), "--generator=pipeline", "--delay_model=unit",
                        f"--pipeline_stages={stages}", "--reset=rst", "--use_system_verilog",
                        f"--output_verilog_path={sv}", *flags, str(tmp / "p.opt.ir")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return True, False, _err(r.stderr), ""
    return True, True, "", sv.read_text()


def _err(s: str) -> str:
    m = re.search(r"Error: (.*)", s)
    return m.group(1)[:200] if m else s[-200:]


# --- F5: several predicated ops on one channel, by strictness ----------------
TWO_SENDS = ("  s: bits[1] = state_read(state_element=s, id=1)\n"
             "  ns: bits[1] = not(s, id=6)\n"
             "  s1: token = send(rt, d, predicate=s, channel=o, id=7)\n"
             "  s2: token = send(rt, d, predicate=ns, channel=o, id=8)\n"
             "  nv: () = next_value(state_element=s, value=ns, id=9)\n")


@needs_xls
@pytest.mark.parametrize("strictness,merges", [
    ("proven_mutually_exclusive", True), ("runtime_mutually_exclusive", True),
    ("arbitrary_static_order", True), ("runtime_ordered", True), ("total_order", False)])
def test_two_predicated_sends_merge(tmp_path, strictness, merges):
    ok_opt, ok_cg, msg, _ = opt_and_codegen(
        tmp_path, _proc(TWO_SENDS, "s: bits[1], init={0}", out_strictness=strictness))
    record(f"two_sends_one_channel.{strictness}", ok_opt and ok_cg, msg)
    assert (ok_opt and ok_cg) == merges, msg


# --- F5: state_read predicate -------------------------------------------------
@needs_xls
def test_state_read_predicate(tmp_path):
    body = ("  b: bits[1] = bit_slice(d, start=0, width=1, id=6)\n"
            "  s: bits[8] = state_read(state_element=s, predicate=b, id=1)\n"
            "  x: bits[8] = add(s, d, id=7)\n"
            "  s1: token = send(rt, x, channel=o, id=8)\n"
            "  nv: () = next_value(state_element=s, value=x, predicate=b, id=9)\n")
    ok_opt, ok_cg, msg, _ = opt_and_codegen(tmp_path, _proc(body, "s: bits[8], init={0}"))
    record("state_read_predicate", ok_opt and ok_cg, msg)
    assert ok_opt and ok_cg, msg


# --- F5: what the lowering's token and strictness choices rest on -----------
def _two_sends(p2: str, chained: bool) -> str:
    return ("  p1: bits[1] = bit_slice(d, start=0, width=1, id=6)\n"
            f"  p2: bits[1] = {p2}\n"
            "  one: bits[8] = literal(value=1, id=10)\n"
            "  d1: bits[8] = add(d, one, id=11)\n"
            "  s1: token = send(rt, d, predicate=p1, channel=o, id=8)\n"
            f"  s2: token = send({'s1' if chained else 'rt'}, d1, predicate=p2, channel=o, id=9)\n")


OVERLAP = "bit_slice(d, start=1, width=1, id=7)"
EXCL = "not(p1, id=7)"


@needs_xls
def test_proven_exclusive_is_checked(tmp_path):
    ok_opt, _, msg, _ = opt_and_codegen(tmp_path, _proc(_two_sends(OVERLAP, False)))
    record("proven_mutually_exclusive.unprovable_rejected", not ok_opt, msg)
    assert not ok_opt and "can be active at the same time" in msg, msg


@needs_xls
@pytest.mark.parametrize("chained", [False, True])
def test_proven_exclusive_chained_or_not_runs_at_ii1(tmp_path, chained):
    ok_opt, ok_cg, msg, _ = opt_and_codegen(tmp_path, _proc(_two_sends(EXCL, chained)))
    record(f"proven_mutually_exclusive.chained={chained}", ok_opt and ok_cg, msg)
    assert ok_opt and ok_cg, msg


@needs_xls
@pytest.mark.parametrize("strictness", ["runtime_mutually_exclusive", "runtime_ordered"])
def test_runtime_exclusive_asserts_and_needs_unordered_ops(tmp_path, strictness):
    """Unchained: codegen emits an assertion that at most one op on the
    channel fires per activation. Token-chained: not schedulable at II=1."""
    ok_opt, ok_cg, msg, sv = opt_and_codegen(
        tmp_path / "u", _proc(_two_sends(OVERLAP, False), out_strictness=strictness))
    assert ok_opt and ok_cg, msg
    asserts = "has active operations on channel o in the same activation" in sv
    _, ok_cg2, msg2, _ = opt_and_codegen(
        tmp_path / "c", _proc(_two_sends(OVERLAP, True), out_strictness=strictness))
    record(f"{strictness}.asserts", asserts)
    record(f"{strictness}.chained_ii1", ok_cg2, msg2)
    assert asserts and not ok_cg2 and "full throughput" in msg2, msg2


@needs_xls
def test_next_value_while_read_disabled_asserts(tmp_path):
    body = ("  b: bits[1] = bit_slice(d, start=0, width=1, id=6)\n"
            "  c: bits[1] = bit_slice(d, start=1, width=1, id=10)\n"
            "  s: bits[8] = state_read(state_element=s, predicate=b, id=1)\n"
            "  x: bits[8] = add(s, d, id=7)\n"
            "  s1: token = send(rt, x, channel=o, id=8)\n"
            "  nv: () = next_value(state_element=s, value=d, predicate=c, id=9)\n")
    ok_opt, ok_cg, msg, sv = opt_and_codegen(tmp_path, _proc(body, "s: bits[8], init={0}"))
    assert ok_opt and ok_cg, msg
    asserts = "fired while read disabled" in sv
    record("next_value.while_read_disabled_asserts", asserts)
    assert asserts


# --- F8: min_delay pins stages -----------------------------------------------
MIN_DELAY = ("  md: token = min_delay(rt, delay=2, id=6)\n"
             "  s1: token = send(md, d, channel=o, id=7)\n" + _UNIT_STATE)


@needs_xls
@pytest.mark.parametrize("stages,ok", [(1, False), (2, False), (3, True)])
def test_min_delay_is_honoured(tmp_path, stages, ok):
    _, ok_cg, msg, _ = opt_and_codegen(tmp_path, _proc(MIN_DELAY), stages=stages)
    record(f"min_delay_2.stages_{stages}", ok_cg, msg)
    assert ok_cg == ok, msg


# --- F3: flow control on a top proc's interface ------------------------------
PASS = "  s1: token = send(rt, d, channel=o, id=7)\n" + _UNIT_STATE


@needs_xls
def test_flow_control_none_still_has_ready(tmp_path):
    ok_opt, ok_cg, msg, sv = opt_and_codegen(tmp_path, _proc(PASS, out_fc="none"))
    assert ok_opt and ok_cg, msg
    has_rdy = re.search(r"input wire o_rdy", sv) is not None
    record("flow_control_none.emits_rdy", has_rdy,
           "valid-only ports need Integrate to tie rdy (RQ-F3)")
    assert has_rdy


@needs_xls
def test_flow_control_valid_is_not_a_value(tmp_path):
    ok_opt, _, msg, _ = opt_and_codegen(tmp_path, _proc(PASS, out_fc="valid"))
    record("flow_control_valid.parses", ok_opt, msg)
    assert not ok_opt and "flow control" in msg


# --- F3: single_value channels (levels) --------------------------------------
_SV_IR = """package p

top proc p<a: bits[8] in, l: bits[8] in, o: bits[8] out, q: bits[8] out>(s: (), init={()}) {
  chan_interface a(direction=receive, kind=streaming, strictness=proven_mutually_exclusive, flow_control=ready_valid, flop_kind=none)
  chan_interface l(direction=receive, kind=single_value, @@STRICT@@flow_control=none, flop_kind=none)
  chan_interface o(direction=send, kind=streaming, strictness=proven_mutually_exclusive, flow_control=ready_valid, flop_kind=none)
  chan_interface q(direction=send, kind=single_value, flow_control=none, flop_kind=none)
  t: token = after_all(id=2)
  r: (token, bits[8]) = receive(t, channel=a, id=3)
  rt: token = tuple_index(r, index=0, id=4)
  d: bits[8] = tuple_index(r, index=1, id=5)
  rl: (token, bits[8]) = receive(rt, channel=l, id=6)
  lt: token = tuple_index(rl, index=0, id=7)
  lv: bits[8] = tuple_index(rl, index=1, id=8)
  x: bits[8] = add(d, lv, id=9)
  s1: token = send(lt, x, channel=o, id=10)
  s2: token = send(s1, x, channel=q, id=11)
  s: () = state_read(state_element=s, id=1)
  nv: () = next_value(state_element=s, value=s, id=12)
}
"""


@needs_xls
def test_single_value_channels_are_data_only_and_registered(tmp_path):
    ok_opt, ok_cg, msg, sv = opt_and_codegen(tmp_path, _SV_IR.replace("@@STRICT@@", ""))
    assert ok_opt and ok_cg, msg
    data_only = re.search(r"input wire \[7:0\] l,", sv) is not None and "l_vld" not in sv \
        and "l_rdy" not in sv and "q_vld" not in sv and "q_rdy" not in sv
    registered = "__l_reg <= l;" in sv and "assign q = __q_reg;" in sv
    record("single_value.data_only", data_only, "a level is a data pin (RQ-F3)")
    record("single_value.registered_both_sides", registered,
           "flop_kind=none still registers a single_value input and output: +1 cycle each")
    assert data_only and registered


@needs_xls
def test_single_value_rejects_a_strictness(tmp_path):
    ok_opt, _, msg, _ = opt_and_codegen(
        tmp_path, _SV_IR.replace("@@STRICT@@", "strictness=proven_mutually_exclusive, "))
    record("single_value.strictness_rejected", not ok_opt, msg)
    assert not ok_opt and "not streaming but has" in msg


# --- W2 exit: two sends in one stage complete separately ---------------------
_TWO_SENDS = """package p

top proc p<a: bits[8] in, c: bits[1] out, o: bits[8] out>(s: (), init={()}) {
  chan_interface a(direction=receive, kind=streaming, strictness=proven_mutually_exclusive, flow_control=ready_valid, flop_kind=none)
  chan_interface c(direction=send, kind=streaming, strictness=proven_mutually_exclusive, flow_control=ready_valid, flop_kind=none)
  chan_interface o(direction=send, kind=streaming, strictness=proven_mutually_exclusive, flow_control=ready_valid, flop_kind=none)
  t: token = after_all(id=2)
  r: (token, bits[8]) = receive(t, channel=a, id=3)
  rt: token = tuple_index(r, index=0, id=4)
  d: bits[8] = tuple_index(r, index=1, id=5)
  one: bits[1] = literal(value=1, id=6)
  s1: token = send(rt, one, channel=c, id=7)
  s2: token = send(s1, d, channel=o, id=8)
  s: () = state_read(state_element=s, id=1)
  nv: () = next_value(state_element=s, value=s, id=9)
}
"""

_TWO_SENDS_TB = """module tb;
  logic clk = 0, rst = 1;
  logic [7:0] a = 8'h11, o; logic a_vld = 1, a_rdy, c, c_vld, c_rdy = 1, o_vld, o_rdy = 0;
  p dut(.*);
  int c_done = -1, a_done = -1;
  initial begin
    repeat (2) begin #5 clk = 1; #5 clk = 0; end
    rst = 0;
    for (int cyc = 0; cyc < 6; cyc++) begin
      if (cyc == 3) o_rdy = 1;
      #1;
      if (c_vld && c_rdy && c_done < 0) c_done = cyc;
      if (a_vld && a_rdy && a_done < 0) a_done = cyc;
      #4 clk = 1; #5 clk = 0;
    end
    $display("R %0d %0d", c_done, a_done);
    $display("X done");
    $finish;
  end
endmodule
"""


@needs_xls
@pytest.mark.verilator
def test_send_completes_before_the_stages_receive(tmp_path):
    """A 1-stage proc: receive a, send c, send o. With o stalled, c's send
    completes at once and a's receive only when o's does: a credit returned
    on c leaves before the value it stands for has left its FIFO."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from xls_harness import have_verilator, run_verilator
    if not have_verilator():
        pytest.skip("needs verilator")
    ok_opt, ok_cg, msg, sv = opt_and_codegen(tmp_path, _TWO_SENDS)
    assert ok_opt and ok_cg, msg
    (tmp_path / "p.sv").write_text(sv)
    (tmp_path / "tb.sv").write_text(_TWO_SENDS_TB)
    out = run_verilator([tmp_path / "p.sv", tmp_path / "tb.sv"], "tb", tmp_path / "sim",
                        with_lib=False)
    (c_done, a_done) = [tuple(int(x) for x in l.split()[1:]) for l in out if l.startswith("R ")][0]
    early = c_done < a_done
    record("multi_send.completes_before_receive", {"send": c_done, "receive": a_done},
           "a same-activation credit return leads the pop by one value: size the "
           "credited FIFO at credits + 1, or keep the data output from backpressuring")
    assert early and a_done == 3, (c_done, a_done)


# --- F8 / per-arc throughput: next_value label= ------------------------------
@needs_xls
def test_next_value_label_parses(tmp_path):
    body = ("  s: bits[8] = state_read(state_element=s, id=1)\n"
            "  x: bits[8] = add(s, d, id=7)\n"
            "  s1: token = send(rt, x, channel=o, id=8)\n"
            "  nv: () = next_value(state_element=s, value=x, label=\"acc\", id=9)\n")
    ok_opt, ok_cg, msg, _ = opt_and_codegen(tmp_path, _proc(body, "s: bits[8], init={0}"))
    record("next_value_label", ok_opt and ok_cg, msg)
    assert ok_opt and ok_cg, msg


# --- F7 / B4e: multi-proc codegen --------------------------------------------
LEAF_DSLX = """\
proc leaf {
  i: chan<u8> in;
  o: chan<u8> out;
  config(i: chan<u8> in, o: chan<u8> out) { (i, o) }
  init { u8:0 }
  next(st: u8) {
    let (tok, v, ok) = recv_non_blocking(join(), i, u8:0);
    let tok = send_if(tok, o, ok, v + st);
    st + u8:1
  }
}
proc top {
  config(a: chan<u8> in, b: chan<u8> out) {
    let (s, r) = chan<u8, u32:2>("mid");
    spawn leaf(a, s);
    spawn leaf(r, b);
  }
  init { () }
  next(st: ()) { () }
}
"""

LOOP_DSLX = """\
proc fwd {
  i: chan<u8> in; o: chan<u8> out; fb_in: chan<u8> in; fb_out: chan<u8> out;
  config(i: chan<u8> in, o: chan<u8> out, fb_in: chan<u8> in, fb_out: chan<u8> out) {
    (i, o, fb_in, fb_out)
  }
  init { () }
  next(st: ()) {
    let (t, v) = recv(join(), i);
    let (t2, f) = recv(t, fb_in);
    let t3 = send(t2, o, v + f);
    let _t4 = send(t3, fb_out, v);
  }
}
proc top {
  config(a: chan<u8> in, b: chan<u8> out) {
    let (fs, fr) = chan<u8, u32:0>("fb");
    spawn fwd(a, b, fr, fs);
  }
  init { () }
  next(st: ()) { () }
}
"""


def _convert(tmp: Path, dslx: str, top: str = "top") -> str:
    conv = find_tool("ir_converter_main")
    if conv is None:
        pytest.skip("needs ir_converter_main")
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "d.x").write_text(dslx)
    r = subprocess.run([conv, f"--top={top}", "--lower_to_proc_scoped_channels",
                        str(tmp / "d.x")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


@needs_xls
def test_multi_proc_default_fifo_module_is_undefined(tmp_path):
    ir_text = _convert(tmp_path, LEAF_DSLX)
    ok_opt, ok_cg, msg, sv = opt_and_codegen(tmp_path / "w", ir_text, "--multi_proc")
    assert ok_opt and ok_cg, msg
    inst = "xls_fifo_wrapper #(" in sv
    defined = re.search(r"^module xls_fifo_wrapper\b", sv, re.M) is not None
    record("multi_proc.default_fifo_module", {"instantiated": inst, "defined": defined},
           "B4e: supply a fifo module or pass --materialize_internal_fifos")
    assert inst and not defined
    _, ok_cg, msg, sv = opt_and_codegen(tmp_path / "m", ir_text, "--multi_proc",
                                        "--materialize_internal_fifos")
    assert ok_cg and "xls_fifo_wrapper" not in sv, msg


@needs_xls
def test_proc_initiation_interval_attribute_is_ignored(tmp_path):
    ir_text = _convert(tmp_path, LEAF_DSLX)
    with_ii = re.sub(r"^(proc __d__leaf)", r"#[initiation_interval(2)]\n\1", ir_text,
                     flags=re.M)
    assert with_ii != ir_text
    flags = ("--multi_proc", "--materialize_internal_fifos")
    _, ok1, m1, sv1 = opt_and_codegen(tmp_path / "a", ir_text, *flags)
    _, ok2, m2, sv2 = opt_and_codegen(tmp_path / "b", with_ii, *flags)
    assert ok1 and ok2, m1 + m2
    same = sv1 == sv2
    record("proc_initiation_interval_attr.ignored_by_multi_proc", same,
           "RQ-F7: one stage/II setting per multi-proc package")
    assert same


@needs_xls
def test_depth0_bypass_self_loop_is_accepted(tmp_path):
    ir_text = _convert(tmp_path, LOOP_DSLX)
    assert "fifo_depth=0, bypass=true" in ir_text
    ok_opt, ok_cg, msg, _ = opt_and_codegen(tmp_path / "l", ir_text, "--multi_proc",
                                            "--materialize_internal_fifos")
    record("depth0_bypass_loopback.accepted", ok_opt and ok_cg,
           "RQ-B3 must reject it; XLS does not")
    assert ok_opt and ok_cg, msg


# --- credit sender shape (RQ-L2) ----------------------------------------------
@needs_xls
def test_nonblocking_receive_ready_waits_on_send(tmp_path):
    """In the credit_tx template the credit-return receive's ready is the
    activation's outputs-ready: a return waits while data is backpressured.
    So the credit sender's data output must never backpressure (valid-only),
    or credit return needs its own proc (RQ-L2)."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent / "templates"))
    import xls_templates as T
    _, ok, msg, sv = opt_and_codegen(tmp_path, T.package("c", T.credit_tx()))
    assert ok, msg
    m = re.search(r"assign cred_in_rdy = (\w+);", sv)
    waits = m is not None and m.group(1).startswith("active_outputs_ready")
    record("nonblocking_receive.ready_is_outputs_ready", waits,
           "credit return couples to data backpressure in one proc")
    assert waits


# --- proc channel registers (RQ-B1 chan_flop, RQ-R1) ---------------------------
@needs_xls
def test_codegen_flop_flags_do_not_register_proc_channels(tmp_path):
    text = _proc(PASS)
    _, ok1, m1, sv_on = opt_and_codegen(tmp_path / "on", text, "--flop_inputs=true",
                                        "--flop_outputs=true")
    _, ok2, m2, sv_off = opt_and_codegen(tmp_path / "off", text, "--flop_inputs=false",
                                         "--flop_outputs=false")
    assert ok1 and ok2, m1 + m2
    same = sv_on == sv_off
    record("codegen_flop_flags.ignored_for_procs", same,
           "proc channel registers come from chan_interface flop_kind")
    assert same


@needs_xls
@pytest.mark.parametrize("kind,ok", [("none", True), ("flop", True), ("skid", True),
                                     ("zero_latency", True), ("zerolatency", False)])
def test_chan_interface_flop_kinds(tmp_path, kind, ok):
    text = _proc(PASS).replace(
        "chan_interface o(direction=send, kind=streaming, strictness=proven_mutually_exclusive, "
        "flow_control=ready_valid, flop_kind=none)",
        "chan_interface o(direction=send, kind=streaming, strictness=proven_mutually_exclusive, "
        f"flow_control=ready_valid, flop_kind={kind})")
    assert f"flop_kind={kind})" in text
    ok_opt, ok_cg, msg, _ = opt_and_codegen(tmp_path, text)
    record(f"chan_interface_flop_kind.{kind}", ok_opt and ok_cg, msg)
    assert (ok_opt and ok_cg) == ok, msg
