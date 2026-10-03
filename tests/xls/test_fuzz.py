"""CH-4 (exhaustive single operators at 1-4 bits) and CH-5 (random
expressions): Verilator, the interpreter and (if present) XLS must agree.

``XLS_FUZZ_BATCHES`` (default 2) sets how many random batches run; each
batch is one Verilator build of ``XLS_FUZZ_FNS`` functions (default 150)
with ``XLS_FUZZ_VECS`` vectors each (default 32).
"""
import os
import random

import pytest

from exprgen import package, random_function, single_op_functions
from xls_harness import FnCheck, check_functions

BATCHES = int(os.environ.get("XLS_FUZZ_BATCHES", "2"))
NFNS = int(os.environ.get("XLS_FUZZ_FNS", "150"))
NVECS = int(os.environ.get("XLS_FUZZ_VECS", "32"))
SEED = int(os.environ.get("XLS_FUZZ_SEED", "2026"))


def edge(rng, w, signed):
    m = (1 << w) - 1
    return rng.choice([0, 1, m, 1 << (w - 1), (1 << (w - 1)) - 1, m - 1]) & m


@pytest.mark.verilator
def test_exhaustive_single_ops(workdir):
    fns = single_op_functions()
    path = workdir / "ex_pkg.sv"
    path.write_text(package("ex_pkg", fns))
    checks = [FnCheck(f.name, exhaustive=True) for f in fns]
    res = check_functions([str(path)], "ex_pkg", checks, workdir)
    assert sum(len(v) for v in res.values()) > 50000


@pytest.mark.verilator
@pytest.mark.parametrize("batch", range(BATCHES))
def test_random_expressions(workdir, batch):
    rng = random.Random(SEED * 1000 + batch)
    fns = [random_function(rng, f"fz{i}") for i in range(NFNS)]
    path = workdir / "fz_pkg.sv"
    path.write_text(package("fz_pkg", fns))
    checks = []
    for f in fns:
        vecs = set()
        space = 1 << sum(a.width for a in f.args)
        while len(vecs) < min(NVECS, space):
            vecs.add(tuple(edge(rng, a.width, a.signed) if rng.random() < 0.35
                           else rng.getrandbits(a.width) for a in f.args))
        checks.append(FnCheck(f.name, sorted(vecs)))
    check_functions([str(path)], "fz_pkg", checks, workdir)
