"""fw_token_pool and fw_slot_reserve: cycle steps, mapped from their step().

* A Python model of each class's per-cycle rules (the classes' headers). The
  model is also the requester and the owner: it puts each token, or each
  reservation, back a few cycles after the grant, and now and then puts back
  one that is not held (misuse).
* The class model against that, and XLS's RTL against the class model,
  cycle for cycle, at 1 and 2 stages.
"""
import random
from pathlib import Path

import pytest

from xls_harness import check_step, have_verilator

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "lib_pool_pkg.sv")
needs_sim = pytest.mark.skipif(not have_verilator(), reason="needs Verilator")

# typedefs in lib_pool_pkg.sv: (N, value bits)
POOLS = {"pool_4": (4, 1), "pool_5": (5, 6), "pool_1": (1, 4), "pool_16": (16, 8)}
# (N, K, value bits)
RESERVES = {"rsv_8": (8, 4, 1), "rsv_6": (6, 3, 6), "rsv_4": (4, 4, 4)}
CYCLES = 80


def ib(n):
    return max(1, (n - 1).bit_length())


def _offered(q, i, cyc):
    return i < len(q) and q[i][0] <= cyc


# --- the per-cycle rules ------------------------------------------------------
def pool_ref(n, w, reqs, cycles, seed, misuse=0.0):
    """reqs: (cycle offered, value), taken in order. Each token granted is
    put back 1 to 4 cycles later; with probability *misuse* a grant also
    puts back a random token. Returns (tok trace, rel schedule)."""
    rng = random.Random(seed)
    held, rels, out = set(), [], []
    ri = li = 0
    for cyc in range(cycles):
        new = set()
        free = [i for i in range(n) if i not in held]
        if free and _offered(reqs, ri, cyc):
            t, v = free[0], reqs[ri][1]
            ri += 1
            out.append((cyc, (t << w) | v))
            new.add(t)
            rels.append((cyc + rng.randint(1, 4), t))
            if rng.random() < misuse:
                rels.append((cyc + rng.randint(1, 4), rng.randrange(n)))
        rm = set()
        if _offered(rels, li, cyc):
            r = rels[li][1]
            li += 1
            if r in held:
                rm.add(r)
        held = (held - rm) | new
    return out, rels


def reserve_ref(n, k, w, reqs, cycles, seed, misuse=0.0):
    """reqs: (cycle offered, {k, value}). One request is held while it waits
    for its slots. Each reservation is released 1 to 4 cycles after its
    grant; with probability *misuse* a grant also releases a random 1..K.
    Returns (gnt trace, rel schedule)."""
    rng = random.Random(seed)
    used, hold, rels, out = 0, None, [], []
    ri = li = 0
    for cyc in range(cycles):
        fr = n - used
        g = None
        if hold is not None and fr >= hold >> w:
            g = hold
        rdy = hold is None or g is not None
        nhold = hold if g is None else None
        if rdy and _offered(reqs, ri, cyc):
            x = reqs[ri][1]
            ri += 1
            if g is None and fr >= x >> w:
                g = x
            else:
                nhold = x
        hold = nhold
        add = sub = 0
        if g is not None:
            out.append((cyc, g))
            add = g >> w
            rels.append((cyc + rng.randint(1, 4), add))
            if rng.random() < misuse:
                rels.append((cyc + rng.randint(1, 4), rng.randint(1, k)))
        if _offered(rels, li, cyc):
            sub = min(rels[li][1], used)
            li += 1
        used += add - sub
    return out, rels


def _reqs(rng, f):
    c, xs, gap = 0, [], rng.choice([1, 2, 4])
    while True:
        c += rng.randint(0, gap)
        if c >= CYCLES - 30:
            return xs
        xs.append((c, f()))


def pool_case(n, w, seed):
    rng = random.Random(seed)
    reqs = _reqs(rng, lambda: rng.randrange(1 << w))
    out, rels = pool_ref(n, w, reqs, CYCLES, seed, misuse=0.15 if seed % 2 else 0.0)
    return {"req": reqs, "rel": rels}, out


def reserve_case(n, k, w, seed):
    rng = random.Random(seed)
    reqs = _reqs(rng, lambda: (rng.randint(1, k) << w) | rng.randrange(1 << w))
    out, rels = reserve_ref(n, k, w, reqs, CYCLES, seed, misuse=0.15 if seed % 2 else 0.0)
    return {"rsv": reqs, "rel": rels}, out


# --- directed checks of the models ---------------------------------------------
def test_pool_ref_lowest_free_and_exhaustion():
    """N = 4, five requests at cycle 0: tokens 0-3 in cycles 0-3, then the
    fifth waits for the first release (token 0, offered at cycle 4 at the
    earliest) and gets token 0 a cycle after it comes back."""
    out, rels = pool_ref(4, 1, [(0, 1)] * 5, 12, seed=0)
    toks = [(c, v >> 1) for c, v in out]
    assert toks[:4] == [(0, 0), (1, 1), (2, 2), (3, 3)]
    back = min(c for c, t in rels if t == 0)
    assert toks[4][1] == 0 and toks[4][0] > max(3, back)


def test_pool_ref_misuse_does_nothing():
    """Every seed with misuse: replaying the grants and the releases as
    taken (in order, one a cycle, from the cycle offered), a token is never
    granted while held, and a release of a free token frees nothing."""
    for seed in range(1, 40, 2):
        sched, out = pool_case(3, 6, seed)
        rels, take, c = sched["rel"], [], -1
        for oc, _ in rels:
            c = max(oc, c + 1)
            take.append(c)
        ev = sorted([(c, 0, v >> 6) for c, v in out] +
                    [(c, 1, t) for c, (_, t) in zip(take, rels) if c < CYCLES])
        held = set()
        for c, kind, t in ev:   # grants first: a release frees from the next cycle
            if kind == 0:
                assert t not in held, (seed, c, t)
                held.add(t)
            else:
                held.discard(t)


def test_reserve_ref_in_order():
    """N = 4: a request for 3, then one for 4, then one for 1. The 4 waits
    for the 3 to come back, and the 1 waits behind the 4 though a slot is
    free."""
    reqs = [(0, (3 << 1)), (0, (4 << 1)), (0, (1 << 1))]
    out, _ = reserve_ref(4, 4, 1, reqs, 20, seed=0)
    ks = [v >> 1 for _, v in out]
    assert ks == [3, 4, 1]
    assert out[1][0] > out[0][0] + 1 and out[2][0] > out[1][0]


def test_reserve_ref_grants_in_order():
    """The grants are the requests, in order, with their values (those the
    run had time for)."""
    for seed in range(20):
        sched, out = reserve_case(6, 3, 6, seed)
        assert out and [x for _, x in sched["rsv"]][:len(out)] == [v for _, v in out], seed


# --- class model and RTL ------------------------------------------------------
@needs_sim
@pytest.mark.parametrize("name", sorted(POOLS))
def test_pool_model_and_rtl(tmp_path, name):
    n, w = POOLS[name]
    for seed in (1, 2, 3):
        sched, want = pool_case(n, w, seed)
        got = check_step([PKG], "lib_pool_pkg", name, sched, CYCLES, tmp_path / f"s{seed}",
                         rtl_stages=(1, 2))
        assert got.get("tok", []) == want, f"seed {seed}"


@needs_sim
@pytest.mark.parametrize("name", sorted(RESERVES))
def test_reserve_model_and_rtl(tmp_path, name):
    n, k, w = RESERVES[name]
    for seed in (1, 2, 3):
        sched, want = reserve_case(n, k, w, seed)
        got = check_step([PKG], "lib_pool_pkg", name, sched, CYCLES, tmp_path / f"s{seed}",
                         rtl_stages=(1, 2))
        assert got.get("gnt", []) == want, f"seed {seed}"
