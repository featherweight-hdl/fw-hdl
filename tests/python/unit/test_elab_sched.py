"""lower_design goes through an engine (zuspec.synth.proc.sched): loops are
kept by translate and placed by the engine; as-written gives the netlist the
front end's own unrolling gives."""
import pytest

from fw.hdl.fe.elab.flow import lower_design

from test_elab_loops import ROUNDS


def logic(v):
    """The netlist without its comments (the header counts the vars, and a
    kept loop's index is one more, unused)."""
    return [l for l in v.splitlines() if not l.lstrip().startswith("//")]


def _src(tmp_path):
    p = tmp_path / "rounds_top.sv"
    p.write_text(ROUNDS)
    return [str(p)]


def test_as_written_is_the_default_and_matches_front_end_unrolling(tmp_path):
    files = _src(tmp_path)
    a = lower_design(files, "rounds_top")
    b = lower_design(files, "rounds_top", options={"keep_loops": False})
    c = lower_design(files, "rounds_top", schedule="as-written")
    assert a.verilog == c.verilog
    assert logic(a.verilog) == logic(b.verilog)


def test_unknown_engine(tmp_path):
    with pytest.raises(ValueError, match="no scheduler named 'nope'"):
        lower_design(_src(tmp_path), "rounds_top", schedule="nope")
