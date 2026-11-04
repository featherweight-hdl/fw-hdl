"""fw_dep_tracker: a cycle step, mapped from its step().

* A Python model of the per-cycle rules (fw_dep_tracker.svh's header): the
  live producers as a list in entry order, and each dependent's producer.
  The model also makes the stimulus: entries and retires are offered in the
  cycle they are taken (both ports are always ready), producers retire out
  of order, some stay live for long while others come and go, and now and
  then a retire names a producer that is not live, or a producer enters
  with a live tag (misuse).
* The class model against that, and XLS's RTL against the class model,
  cycle for cycle (ok, a level, as a trace of its changes), at 1 and 2
  stages.
"""
import random
from pathlib import Path

import pytest

from xls_harness import check_step, have_verilator

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "lib_dep_pkg.sv")
needs_sim = pytest.mark.skipif(not have_verilator(), reason="needs Verilator")

# typedefs in lib_dep_pkg.sv: (N producers, M dependents)
CLASSES = {"dep_4_4": (4, 4), "dep_8_6": (8, 6), "dep_1_2": (1, 2), "dep_5_3": (5, 3)}
CYCLES = 120


def ib(n):
    return max(1, (n - 1).bit_length())


# --- the per-cycle rules ------------------------------------------------------
def dep_ref(n, m, ent, ret, cycles):
    """ent: {cycle: (kind, tag)}, ret: {cycle: tag}, each taken in its cycle.
    Returns the ok trace: (cycle, bits) each time ok changes, from 0."""
    live, on, wait = [], [None] * m, [False] * m
    out, last = [], 0
    for cyc in range(cycles):
        top = live[-1] if live else None
        r = ret.get(cyc)
        rv = r is not None and r in live
        if rv:
            live.remove(r)
        e = ent.get(cyc)
        if e is not None and e[0] == 0 and e[1] not in live:
            live.append(e[1])
        if e is not None and e[0] == 1:
            on[e[1]], wait[e[1]] = top, top is not None
        for d in range(m):
            if wait[d] and rv and on[d] == r:
                wait[d] = False
        ok = sum(1 << d for d in range(m) if not wait[d])
        if ok != last:
            out.append((cyc, ok))
            last = ok
    return out


def gen(n, m, seed, cycles=CYCLES):
    """Random entries and retires (see the module docstring)."""
    rng = random.Random(seed)
    p_ent = rng.choice([0.4, 0.7, 0.9])
    ent, ret, due = {}, {}, []
    live = set()
    for cyc in range(cycles - 20):
        if rng.random() < p_ent:
            free = [t for t in range(n) if t not in live]
            if rng.random() < 0.5 and (free or rng.random() < 0.1):
                t = rng.choice(free) if free and rng.random() > 0.05 else rng.randrange(n)
                ent[cyc] = (0, t)
                if t not in live:
                    live.add(t)
                    hold = rng.randint(20, 60) if rng.random() < 0.15 else rng.randint(1, 8)
                    due.append((cyc + hold, t))
            else:
                ent[cyc] = (1, rng.randrange(m))
        due.sort()
        if due and due[0][0] <= cyc:
            ret[cyc] = due.pop(0)[1]
            live.discard(ret[cyc])
        elif rng.random() < 0.03:
            ret[cyc] = rng.randrange(n)          # often not live
            if ret[cyc] in live:
                live.discard(ret[cyc])
                due = [x for x in due if x[1] != ret[cyc]]
    return ent, ret


def sched(ent, ret, n, m):
    i = ib(max(n, m))
    return {"ent": [(c, (k << i) | t) for c, (k, t) in sorted(ent.items())],
            "ret": sorted(ret.items())}


# --- directed checks of the model ----------------------------------------------
def test_ref_sticky_and_youngest():
    """Producers 0 then 1 enter; dependent 0 waits on 1 (the youngest).
    Retiring 1 releases it though 0 is still live; dependent 1, entering
    after, waits on 0."""
    ent = {0: (0, 0), 1: (0, 1), 2: (1, 0), 4: (1, 1)}
    got = dep_ref(4, 2, ent, {3: 1}, 8)
    # ok: 0b11 at reset is 0 in the trace's terms, so the first change is
    # from 0: dependent 1 not waiting, dependent 0 waiting (cycle 2).
    assert got == [(0, 0b11), (2, 0b10), (3, 0b11), (4, 0b01)]


def test_ref_same_cycle_retire_releases():
    """Dependent 0 enters in the cycle producer 2 (the youngest) retires: it
    records 2, and the retire releases it at once."""
    got = dep_ref(4, 1, {0: (0, 2), 1: (1, 0)}, {1: 2}, 4)
    assert got == [(0, 1)]


def test_ref_long_lived_producer_keeps_its_place():
    """Producer 0 stays live while 1, 2 and 3 enter and retire many times;
    a dependent then waits on 0, the only live producer."""
    ent, ret = {0: (0, 0)}, {}
    c = 1
    for _ in range(20):
        for t in (1, 2, 3):
            ent[c] = (0, t)
            ret[c + 1] = t
            c += 2
    ent[c + 2] = (1, 0)
    got = dep_ref(4, 1, ent, ret, c + 6)
    assert got[-1] == (c + 2, 0)


def test_gen_drives_every_rule():
    """Across the seeds the RTL runs, the stimulus has a dependent released
    while an older producer is still live (sticky), a retire of a producer
    that is not live, and a producer entering with a live tag."""
    sticky = bad_ret = bad_ent = 0
    for seed in (1, 2, 3):
        ent, ret = gen(5, 3, seed)
        live, on = [], {}
        for cyc in range(CYCLES):
            top = live[-1] if live else None
            r = ret.get(cyc)
            if r is not None:
                if r in live:
                    live.remove(r)
                    sticky += sum(1 for p in on.values() if p == r and live)
                    on = {d: p for d, p in on.items() if p != r}
                else:
                    bad_ret += 1
            e = ent.get(cyc)
            if e and e[0] == 0:
                if e[1] in live:
                    bad_ent += 1
                else:
                    live.append(e[1])
            elif e and top is not None:
                on[e[1]] = top
    assert sticky and bad_ret and bad_ent, (sticky, bad_ret, bad_ent)


# --- class model and RTL ------------------------------------------------------
@needs_sim
@pytest.mark.parametrize("name", sorted(CLASSES))
def test_model_and_rtl(tmp_path, name):
    n, m = CLASSES[name]
    for seed in (1, 2, 3):
        ent, ret = gen(n, m, seed)
        got = check_step([PKG], "lib_dep_pkg", name, sched(ent, ret, n, m), CYCLES,
                         tmp_path / f"s{seed}", rtl_stages=(1, 2))
        assert got.get("ok", []) == dep_ref(n, m, ent, ret, CYCLES), f"seed {seed}"
