"""F5c route (ii) spike: zuspec-synth's DelayEngine.place on f = a*b + c
(python/fw/hdl/spikes/delay_proc.py)."""
import pytest

from fw.hdl.spikes import delay_proc as D

UNIT = D.DelayModel.load("unit")


@pytest.mark.parametrize("w", [8, 16, 32])
def test_runs_and_unit_depth(w):
    r = D.run(w, D.f_depth(w, UNIT))
    assert r.f_depth == 2                 # mul, add: one level each
    assert r.edges >= 0 and r.stage_delay


@pytest.mark.parametrize("w", [8, 16, 32])
@pytest.mark.parametrize("model", [UNIT, D.width_model()], ids=["unit", "width"])
def test_smaller_budget_at_least_as_many_stages(w, model):
    """Down to the slowest single operator (the multiply), a smaller budget
    never gives f fewer stages."""
    fd = D.f_depth(w, model)
    rs = [D.run(w, fd / k, model) for k in (1, 2, 3)]
    mul = D._Arrival(model, {"x"}, {}, 0).of(
        D.T.mul(D.T.var("x", 2 * w), D.T.var("y", 2 * w)))
    feasible = [r for r in rs if r.budget >= mul]
    assert all(b.f_stages >= a.f_stages for a, b in zip(feasible, feasible[1:]))


def test_cuts_only_at_operator_boundaries():
    """The split is one operator per assignment: a cut never goes inside the
    multiply; a budget below it is reported, not met."""
    r = D.run(8, 1.0)
    assert "mul / add" in r.cuts and not r.violations
    r = D.run(8, 16, D.width_model())     # the multiply alone costs 32
    assert r.cuts == ["mul / add"]
    assert any("p_dly0" in v for v in r.violations)
