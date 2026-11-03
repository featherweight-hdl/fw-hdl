"""fw_credit_tx: the class model against a Python model of its per-cycle
rules, and XLS's RTL against the class model cycle for cycle (stages 1 and 2;
I/O flops on and off).

Stimulus is closed-loop: the Python model runs first, and every credit it
spends comes back on ``cr`` a random delay later, so the returns are ones a
real receiver could make. The input arrivals and those returns are then
replayed, as fixed schedules, into the class model and the RTL.
"""
import random
from pathlib import Path

import pytest

import yaml

from fw.hdl.lib import xls_ir
from fw.hdl.verif.canon import Event, Rule, check
from zuspec.be.xls.testing.xlstools import CodegenOptions, codegen_main, opt_main, run_codegen
from xls_harness import _trace, check_step, have_verilator, rtl_step_testbench, run_verilator

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "lib_credit_pkg.sv")
CONTRACT = yaml.safe_load((HERE.parents[2] / "src" / "std" / "credit" /
                           "fw_credit_tx.yaml").read_text())

needs_sim = pytest.mark.skipif(not have_verilator(), reason="needs Verilator")
needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")

# typedef in lib_credit_pkg.sv: (width, CREDITS, NVC, RESERVE, POLICY, CHECK)
CONFIGS = {
    "ctx_1": (8, 4, 1, 0, "pool", 1),
    "ctx_1c4": (8, 8, 1, 0, "pool", 4),
    "ctx_3p": (8, 6, 3, 1, "pool", 1),
    "ctx_3v": (8, 9, 3, 2, "vc", 2),
    "ctx_3s": (8, 2, 3, 1, "pool", 1),
    "ctx_4": (6, 5, 4, 0, "vc", 1),
}
CYCLES = 80


class Src:
    """A harness source: values in push order, each offered from its cycle
    until it is taken."""

    def __init__(self, sched=()):
        self.sched = list(sched)
        self.i = 0

    def ready(self, cyc):
        return self.i < len(self.sched) and self.sched[self.i][0] <= cyc

    def pop(self):
        self.i += 1
        return self.sched[self.i - 1][1]


def credit_ref(cfg, arrivals, cycles, seed, returns=True):
    """The per-cycle rules of fw_credit_tx (see its header), against a
    receiver that returns each spent credit 1-4 cycles after the send (none
    if not *returns*).

    Returns (output trace, the returns made, credits outstanding after each
    cycle)."""
    w, credits, nvc, reserve, policy, check = cfg
    rng = random.Random(seed)
    ins = [Src(s) for s in arrivals]
    cr = Src()
    res, left = [], credits
    for v in range(nvc):
        res.append(min(left, reserve))
        left -= res[-1]
    pool = max(credits - nvc * reserve, 0)
    hold, hv, last = [0] * nvc, [False] * nvc, nvc - 1
    out, outstanding = [], []
    for cyc in range(cycles):
        g = None
        if nvc == 1:
            if pool + res[0] >= check and ins[0].ready(cyc):
                g = 0
                out.append((cyc, ins[0].pop()))
        else:
            for k in range(1, nvc + 1):
                v = (last + k) % nvc
                if hv[v] and pool + res[v] >= check:
                    g = v
                    break
            if g is not None:
                out.append((cyc, (g << w) | hold[g]))
                hv[g], last = False, g
        if g is not None:
            if policy == "pool":
                a = min(pool, check)
                pool, res[g] = pool - a, res[g] - (check - a)
            else:
                a = min(res[g], check)
                res[g], pool = res[g] - a, pool - (check - a)
            # Return times never go back: the source is a FIFO.
            t = cr.sched[-1][0] if cr.sched else 0
            for _ in range(check if returns else 0):
                t = max(t, cyc + rng.randint(1, 4))
                cr.sched.append((t, g))
        if nvc > 1:
            for k in range(nvc):
                if not hv[k] and ins[k].ready(cyc):
                    hold[k], hv[k] = ins[k].pop(), True
        if cr.ready(cyc):
            r = cr.pop()
            if res[r] < reserve:
                res[r] += 1
            else:
                pool += 1
        assert pool >= 0 and all(0 <= x <= reserve for x in res)
        outstanding.append(credits - pool - sum(res))
    return out, cr.sched, outstanding


def stimulus(cfg, cycles, seed):
    """Random arrivals per VC, in bursts and gaps."""
    w, _, nvc, *_ = cfg
    rng = random.Random(seed)
    arrivals = []
    for _ in range(nvc):
        c, s = 0, []
        for _ in range(rng.randint(cycles // 6, cycles // 3)):
            c += rng.choice([0, 0, 1, 1, 2, 5])
            s.append((c, rng.randrange(1 << w)))
        arrivals.append(s)
    return arrivals


def run_ref(cfg, cycles, seed):
    """(output trace, schedule to replay, credits outstanding per cycle)."""
    arrivals = stimulus(cfg, cycles, seed)
    out, returns, outstanding = credit_ref(cfg, arrivals, cycles, seed)
    sched = {f"in_{v}": s for v, s in enumerate(arrivals)}
    sched["cr"] = returns
    return out, sched, outstanding


# --- the Python model's own properties -----------------------------------------
@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_ref_never_overspends(name):
    cfg = CONFIGS[name]
    for seed in range(20):
        out, _, outstanding = run_ref(cfg, CYCLES, seed)
        assert max(outstanding) <= cfg[1]        # the contract's credits_out_max
        assert len(out) * cfg[5] - outstanding[-1] >= 0


def test_ref_reserve_keeps_a_vc_moving():
    """With the pool and its own reserve spent, VC 0 waits; VC 1 still sends
    on its reserve."""
    cfg = (8, 3, 2, 1, "pool", 1)          # pool 1, reserves 1 and 1
    arr = [[(0, 1), (0, 2), (0, 3)], [(3, 9)]]
    out, *_ = credit_ref(cfg, arr, 8, seed=0, returns=False)
    assert out == [(1, 1), (2, 2), (4, (1 << 8) | 9)]


@pytest.mark.parametrize("policy,want", [
    # pool first: VC 0 spends the pool and keeps its reserve; VC 1's
    # second value finds neither pool nor reserve.
    ("pool", [(1, 1), (2, (1 << 8) | 8)]),
    # VC first: VC 0 spends its reserve and leaves the pool for VC 1.
    ("vc", [(1, 1), (2, (1 << 8) | 8), (3, (1 << 8) | 9)]),
])
def test_ref_policy_order(policy, want):
    cfg = (8, 3, 2, 1, policy, 1)
    out, *_ = credit_ref(cfg, [[(0, 1)], [(0, 8), (0, 9)]], 8, seed=0, returns=False)
    assert out == want


def contract_errors(cfg, sched, out):
    """The contract's order rule on one run. The i-th value out on VC v is
    item (v, i); it entered as the i-th arrival on in[v]. A value out of
    order on its VC then leaves with another item's data. Only values that
    left are entered, so a run cut short is not a loss."""
    w = cfg[0]
    ev, n = [], {}
    for c, v in out:
        vc, i = v >> w, n.get(v >> w, 0)
        n[vc] = i + 1
        at, x = sched[f"in_{vc}"][i]
        ev.append(Event("in", "in", at, (vc << 16) | i, key=vc, data=x))
        ev.append(Event("out", "out", c, (vc << 16) | i, key=vc, data=v & ((1 << w) - 1)))
    ev.sort(key=lambda e: (e.cyc, e.ev != "in"))
    return check(ev, Rule.from_dict(CONTRACT["order"]))


# --- class model and RTL --------------------------------------------------------
@needs_sim
@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_model_and_rtl(tmp_path, name):
    cfg = CONFIGS[name]
    # Seed 1: 1 and 2 stages, XLS's default flops. Seed 2: no I/O flops.
    for seed, flags in ((1, ()), (2, ("--flop_inputs=false", "--flop_outputs=false"))):
        want, sched, _ = run_ref(cfg, CYCLES, seed)
        got = check_step([PKG], "lib_credit_pkg", name, sched, CYCLES, tmp_path / f"s{seed}",
                         rtl_stages=(1, 2) if seed == 1 else (1,), rtl_flags=(flags,))
        assert got.get("out", []) == want, f"seed {seed}"
        assert contract_errors(cfg, sched, got.get("out", [])) == [], f"seed {seed}"


@needs_sim
@needs_xls
def test_one_vc_matches_the_template(tmp_path):
    """NVC = 1 behaves as the credit_tx template, cycle for cycle (the
    template's output has no VC bit)."""
    cfg = CONFIGS["ctx_1"]
    want, sched, _ = run_ref(cfg, CYCLES, 3)
    pkg = xls_ir.package("t", xls_ir.credit_tx(width=8, credits=4, cbits=3, name="t"))
    res = run_codegen(pkg, CodegenOptions(), stages=1)
    (tmp_path / "t.sv").write_text(res.verilog)
    tsched = {"data_in": sched["in_0"], "cred_in": [(c, 1) for c, _ in sched["cr"]]}
    (tmp_path / "tb.sv").write_text(rtl_step_testbench(res.signature, tsched, CYCLES))
    got = _trace(run_verilator([tmp_path / "t.sv", tmp_path / "tb.sv"], "xh_rtl_step_tb",
                               tmp_path / "rtl", with_lib=False))
    assert got.get("data_out", []) == want
