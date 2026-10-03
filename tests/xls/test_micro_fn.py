"""CH-1 / CH-4: every expression and statement row of xls-phase0.md §3 as a
pure SV function; Verilator, the interpreter and (if present) XLS must agree.

Vectors are exhaustive when the arguments total 12 bits or fewer, else edge
values plus random ones.
"""
import itertools
import random
from pathlib import Path

import pytest

from fw.hdl.xls_flow import sv_to_functions
from xls_harness import FnCheck, check_functions, check_functions_lrm

HERE = Path(__file__).resolve().parent
PKG = str(HERE / "micro" / "micro_fn_pkg.sv")

FUNCS = [
    "e1_add", "e1_add_ext", "e1_sub", "e1_mul", "e1_smul", "e1_mixed",
    "e2_div", "e2_mod", "e2_sdiv", "e2_smod",
    "e3_bits", "e4_shl", "e4_shr", "e5_ashr", "e5_ashr_ext", "e5_ashr_unsigned",
    "e6_cmp", "e7_logic", "e8_red", "e9_sel", "e10_cat",
    "e11_bit", "e12_part", "e13_idx_up", "e13_idx_dn",
    "e14_cast", "e14_signed", "e14_trunc", "e15_field", "e16_pat",
    "e17_tbl", "e18_arr", "e19_call", "e20_lit",
    "t5_pk", "t6_enum", "s3_case", "s4_pop", "s4_rev", "s6_early", "s8_ops",
]


def edge_values(w):
    vals = {0, 1, 2, (1 << w) - 1, (1 << w) - 2, 1 << (w - 1), (1 << (w - 1)) - 1}
    if w >= 32:
        # around the in-range indices for an `int` index: negatives, small positives
        vals |= {(1 << w) - k for k in range(1, 6)} | set(range(0, 20))
    return sorted(v & ((1 << w) - 1) for v in vals)


def vectors_for(widths, n=96, seed=0):
    if sum(widths) <= 12:
        return list(itertools.product(*[range(1 << w) for w in widths]))
    rng = random.Random(seed)
    edges = [edge_values(w) for w in widths]
    out = set(itertools.islice(itertools.product(*edges), 200))
    while len(out) < 200 + n:
        out.add(tuple(rng.choice(e) if rng.random() < 0.3 else rng.getrandbits(w)
                      for e, w in zip(edges, widths)))
    return sorted(out)


#: Verilator does not follow LRM 11.5.1 for an out-of-range select on a *packed*
#: vector: it wraps the index (x[8] of a bit [7:0] reads x[0]) where the LRM
#: says 0 for a 2-state operand. Unpacked arrays are fine. So these vectors stay
#: in range here; the out-of-range cases are pinned against an LRM model in
#: zuspec-be-xls (test_lower_fn.py: test_e12_e13_*, test_e11_*).
IN_RANGE = {
    "e11_bit": lambda x, i, j: 0 <= j < 8,
    "e13_idx_up": lambda x, i: 0 <= _s32(i) <= 12,
    "e13_idx_dn": lambda x, i: 3 <= i <= 15,
}


def _s32(v):
    return v - (1 << 32) if v >> 31 else v


@pytest.mark.verilator
def test_micro_functions(workdir):
    fns = {f.name: f for f in sv_to_functions([PKG], FUNCS)}
    checks = []
    for i, name in enumerate(FUNCS):
        widths = [a.datatype.bits for a in fns[name].args.args]
        vecs = vectors_for(widths, seed=i)
        if name in IN_RANGE:
            vecs = [v for v in vecs if IN_RANGE[name](*v)]
            vecs += [v for v in vectors_for(widths, n=400, seed=i + 1000)
                     if IN_RANGE[name](*v)][:64]
        checks.append(FnCheck(name=name, vectors=sorted(set(vecs))))
    check_functions([PKG], "micro_fn_pkg", checks, workdir)


def test_lrm_pins_where_verilator_differs():
    # Verilator 5.049 evaluates `b ~^ 1` / `~(b ^ 1)` at 1 bit in a condition
    # (xls-phase0.md §11, 2026-10-03); the LRM makes them 32 bits wide, so true.
    check_functions_lrm([str(HERE / "micro" / "lrm_pins_pkg.sv")], {
        "c_xnor": [((0,), 7), ((1,), 7)],
        "c_not_xor": [((0,), 7), ((1,), 7)],
        "c_if_xnor": [((0,), 7), ((1,), 7)],
        "fz973": [((0x40000000,), 0xc0000000)],
        "fz174": [((1, 0xffff, 0), 1)],
    })
