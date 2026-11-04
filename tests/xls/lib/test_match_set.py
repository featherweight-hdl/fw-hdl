"""fw_match_set: static functions, called in the user's step.

* A Python model of the functions (fw_match_set.svh's header).
* Each function at fixed sizes (lib_match_pkg's wrappers): Verilator, the
  interpreter and XLS agree, on every argument at 3 slots of 2 bits and at
  1 slot, and on random sets with repeated and invalid members at 5 slots
  of 16 bits; and all match the model.
* A filter step that calls it: the match is an invoked function in the
  step's proc, and the class model and the RTL agree cycle for cycle, at 1
  and 2 stages.
"""
import random
import re
from pathlib import Path

import pytest

from fw.hdl.xls_flow import sv_to_xls
from zuspec.be.xls.printer import format_package
from xls_harness import FnCheck, check_functions, check_step, have_verilator

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "lib_match_pkg.sv")
needs_sim = pytest.mark.skipif(not have_verilator(), reason="needs Verilator")


# --- the functions ------------------------------------------------------------
def hits(k, w, keys, valid, q):
    """keys packed, slot i at bits [i*w +: w]."""
    return sum(1 << i for i in range(k)
               if valid >> i & 1 and (keys >> (i * w)) & ((1 << w) - 1) == q)


def first(k, w, keys, valid, q):
    h = hits(k, w, keys, valid, q)
    return (h & -h).bit_length() - 1 if h else 0


REF = {
    "m3_hits": lambda *a: hits(3, 2, *a),
    "m3_any": lambda *a: int(hits(3, 2, *a) != 0),
    "m3_first": lambda *a: first(3, 2, *a),
    "m1_any": lambda *a: int(hits(1, 2, *a) != 0),
    "m1_first": lambda *a: first(1, 2, *a),
    "m5_hits": lambda *a: hits(5, 16, *a),
    "m5_first": lambda *a: first(5, 16, *a),
}


def test_ref():
    keys = 0b10_01_10                    # slots 0, 1, 2 hold 2, 1, 2
    assert hits(3, 2, keys, 0b111, 2) == 0b101
    assert first(3, 2, keys, 0b111, 2) == 0
    assert first(3, 2, keys, 0b110, 2) == 2
    assert hits(3, 2, keys, 0b101, 1) == 0     # held only by an invalid slot
    assert first(3, 2, keys, 0, 2) == 0


def m5_vectors(n=400, seed=5):
    """Sets drawn from a few values, so slots repeat; q is often a member,
    sometimes only of an invalid slot, sometimes of none."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        pool = [rng.getrandbits(16) for _ in range(rng.choice([1, 2, 5]))]
        slots = [rng.choice(pool) for _ in range(5)]
        keys = sum(v << (16 * i) for i, v in enumerate(slots))
        valid = rng.getrandbits(5)
        q = rng.choice(slots) if rng.random() < 0.8 else rng.getrandbits(16)
        out.append((keys, valid, q))
    return out


@pytest.mark.verilator
def test_functions(workdir):
    checks = [FnCheck(name=n, exhaustive=True) for n in REF if not n.startswith("m5")]
    checks += [FnCheck(name=n, vectors=m5_vectors()) for n in ("m5_hits", "m5_first")]
    got = check_functions([PKG], "lib_match_pkg", checks, workdir)
    for chk in checks:
        want = [REF[chk.name](*v) for v in chk.vectors]
        assert got[chk.name] == want, chk.name
    # The random sets have several hits, and a member only of an invalid slot.
    hs = [hits(5, 16, *v) for v in m5_vectors()]
    assert any(bin(h).count("1") > 1 for h in hs)
    assert any(h == 0 and hits(5, 16, k, 0b11111, q) for (k, _, q), h in zip(m5_vectors(), hs))


# --- called in a step ---------------------------------------------------------
def filter_ref(sets, ins, cycles):
    """set: {cycle: (slot, valid, value)}, in: {cycle: value}, each taken in
    its cycle. A value is matched against the set at the start of the cycle."""
    keys, valid, out = [0] * 4, [0] * 4, []
    for cyc in range(cycles):
        x = ins.get(cyc)
        if x is not None:
            h = [i for i in range(4) if valid[i] and keys[i] == x]
            out.append((cyc, (int(bool(h)) << 10) | ((h[0] if h else 0) << 8) | x))
        s = sets.get(cyc)
        if s is not None:
            keys[s[0]], valid[s[0]] = s[2], s[1]
    return {"out": out}


def filter_stim(seed, cycles=100):
    rng = random.Random(seed)
    vals = [rng.getrandbits(8) for _ in range(5)]
    sets = {c: (rng.randrange(4), int(rng.random() < 0.8), rng.choice(vals))
            for c in range(cycles - 10) if rng.random() < 0.3}
    ins = {c: rng.choice(vals) if rng.random() < 0.85 else rng.getrandbits(8)
           for c in range(cycles - 10) if rng.random() < 0.7}
    return sets, ins


def test_filter_invokes_the_match():
    txt = format_package(sv_to_xls([PKG], "match_filter"))
    assert re.search(r"^fn any\b", txt, re.M) and re.search(r"^fn first\b", txt, re.M)
    assert "to_apply=any" in txt and "to_apply=first" in txt


@needs_sim
@pytest.mark.parametrize("seed", [1, 2])
def test_filter_model_and_rtl(tmp_path, seed):
    sets, ins = filter_stim(seed)
    sched = {"set": [(c, (s << 9) | (v << 8) | x) for c, (s, v, x) in sorted(sets.items())],
             "in": sorted(ins.items())}
    got = check_step([PKG], "lib_match_pkg", "match_filter", sched, 100, tmp_path,
                     rtl_stages=(1, 2))
    want = filter_ref(sets, ins, 100)
    assert got == want
    assert any(v >> 10 for _, v in want["out"]) and not all(v >> 10 for _, v in want["out"])
