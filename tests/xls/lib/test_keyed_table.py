"""fw_keyed_table: an all-or-nothing cycle step, mapped from its step().

* A Python model of the per-cycle rules (fw_keyed_table.svh's header): the
  table as a dict, the cycle's requests applied as lookup, install, write,
  remove, each against the table at the start of the cycle.
* The class model against that, and XLS's RTL against the class model, cycle
  for cycle, with both responses back-pressured at random: a response goes
  as soon as its port is ready, even while the other stalls the step.
"""
import random
from pathlib import Path

import pytest

from xls_harness import check_step, have_verilator

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "lib_table_pkg.sv")
needs_sim = pytest.mark.skipif(not have_verilator(), reason="needs Verilator")

# typedef in lib_table_pkg.sv: (key bits, value bits, N)
CLASSES = {"tbl_4": (4, 8, 4), "tbl_16": (6, 8, 16), "tbl_5": (4, 6, 5), "tbl_1": (4, 8, 1)}
CYCLES = 80


def sb(n):
    return max(1, (n - 1).bit_length())


# --- the per-cycle rules ------------------------------------------------------
def table_ref(kw, vw, n, sched, cycles, stalls):
    """The table is n slots of (key, value) or None. A request offered at
    cycle c may be taken from c on, one per port per cycle. Each response
    goes when its port is ready, once: if the other stalls, the cycle takes
    nothing and changes nothing, and the response already sent is not sent
    again when the cycle is retried."""
    s = sb(n)
    pend = {p: list(sched.get(p, [])) for p in ("ins", "lkp", "wr", "rm")}
    slots = [None] * n
    out = {"ins_rsp": [], "lkp_rsp": []}
    sent = set()
    for cyc in range(cycles):
        req = {p: q[0][1] for p, q in pend.items() if q and q[0][0] <= cyc}
        nxt = list(slots)
        rsp = {}
        if "lkp" in req:
            hit = [i for i, e in enumerate(slots) if e and e[0] == req["lkp"]]
            sl, v = (hit[0], slots[hit[0]][1]) if hit else (0, 0)
            rsp["lkp_rsp"] = (bool(hit) << (s + vw)) | (sl << vw) | v
        if "ins" in req:
            k, v = req["ins"] >> vw, req["ins"] & ((1 << vw) - 1)
            dup = any(e and e[0] == k for e in slots)
            free = [i for i, e in enumerate(slots) if e is None]
            ok = not dup and bool(free)
            if ok:
                nxt[free[0]] = (k, v)
            full = not dup and not free
            rsp["ins_rsp"] = (ok << (s + 1)) | (full << s) | (free[0] if ok else 0)
        if "wr" in req:
            i, v = req["wr"] >> vw, req["wr"] & ((1 << vw) - 1)
            if i < n and slots[i]:
                nxt[i] = (nxt[i][0], v)
        if "rm" in req and req["rm"] < n and slots[req["rm"]]:
            nxt[req["rm"]] = None
        stalled = False
        for o, v in rsp.items():
            if o in sent:
                continue
            if cyc in stalls.get(o, ()):
                stalled = True
            else:
                out[o].append((cyc, v))
                sent.add(o)
        if stalled:
            continue
        sent.clear()
        slots = nxt
        for p in req:
            pend[p].pop(0)
    return {p: t for p, t in out.items() if t}


def gen(kw, vw, n, seed):
    """Random requests on every port: keys from a few more than n, so
    installs hit duplicates and a full table, and lookups hit and miss;
    write and remove name any slot, live or not."""
    rng = random.Random(seed)
    nk = min(1 << kw, n + 3)
    vals = {"ins": lambda: (rng.randrange(nk) << vw) | rng.randrange(1 << vw),
            "lkp": lambda: rng.randrange(nk),
            "wr": lambda: (rng.randrange(1 << sb(n)) << vw) | rng.randrange(1 << vw),
            "rm": lambda: rng.randrange(1 << sb(n))}
    sched = {}
    for p, f in vals.items():
        c, xs, gap = 0, [], rng.choice([1, 2, 4])
        while True:
            c += rng.randint(0, gap)
            if c >= CYCLES - 20:
                break
            xs.append((c, f()))
        sched[p] = xs
    p = rng.choice([0.2, 0.5]) if seed % 3 else 0.0
    stalls = {o: sorted(c for c in range(CYCLES) if rng.random() < p)
              for o in ("ins_rsp", "lkp_rsp")}
    return sched, stalls


def ins(k, v):
    return (k << 8) | v


def test_ref_same_cycle():
    """N = 4. Cycles 0-3 install keys 1-4 (slots 0-3). Cycle 4: lookup of key 2
    sees the old value under a write to slot 1, an install of key 9 finds the
    table full though slot 0 is removed in the same cycle. Cycle 5: key 9 takes
    slot 0, and a lookup of key 9 misses (it is installed this cycle);
    cycle 6 it hits."""
    sched = {"ins": [(c, ins(c + 1, 0x10 + c)) for c in range(4)] + [(4, ins(9, 0x99)),
                                                                    (5, ins(9, 0x99))],
             "lkp": [(4, 2), (5, 9), (6, 9)],
             "wr": [(4, (1 << 8) | 0xee)],
             "rm": [(4, 0)]}
    got = table_ref(4, 8, 4, sched, 8, {})
    assert got["ins_rsp"] == [(0, 0b1_0_00), (1, 0b1_0_01), (2, 0b1_0_10), (3, 0b1_0_11),
                              (4, 0b0_1_00), (5, 0b1_0_00)]
    hit = lambda sl, v: (1 << 10) | (sl << 8) | v
    assert got["lkp_rsp"] == [(4, hit(1, 0x11)), (5, 0), (6, hit(0, 0x99))]


def test_ref_stall_takes_nothing():
    """lkp_rsp stalls in cycles 0 and 1. The install's response goes in
    cycle 0, once, but key 3 is installed only in cycle 2, with the lookup
    taken: so the lookup misses, and a lookup in cycle 3 hits."""
    sched = {"ins": [(0, ins(3, 0x33))], "lkp": [(0, 3), (0, 3)]}
    got = table_ref(4, 8, 4, sched, 4, {"lkp_rsp": [0, 1]})
    assert got == {"ins_rsp": [(0, 0b1_0_00)],
                   "lkp_rsp": [(2, 0), (3, (1 << 10) | 0x33)]}


# --- class model and RTL ------------------------------------------------------
@needs_sim
@pytest.mark.parametrize("name", sorted(CLASSES))
def test_model_and_rtl(tmp_path, name):
    """Seed 3 has both responses always ready, at 1 and 2 stages (a step's
    receives share a stage, so each activation is one cycle's requests);
    seeds 1 and 2 stall them at random."""
    kw, vw, n = CLASSES[name]
    for seed in (1, 2, 3):
        sched, stalls = gen(kw, vw, n, seed)
        quiet = not any(stalls.values())
        got = check_step([PKG], "lib_table_pkg", name, sched, CYCLES, tmp_path / f"s{seed}",
                         rtl_stages=(1, 2) if quiet else (1,), stalls=stalls)
        want = table_ref(kw, vw, n, sched, CYCLES, stalls)
        assert got == want, f"seed {seed}"
