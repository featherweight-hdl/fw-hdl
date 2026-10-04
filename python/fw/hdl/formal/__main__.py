"""``python -m fw.hdl.formal``: prove SVUnit tests for every input.

    python -m fw.hdl.formal examples/xls/crc32/crc32_pkg.sv \\
        --api crc32_pkg::main --tests examples/xls/crc32/crc32_unit_test.sv

*design* holds the design's files, ``--tests`` the SVUnit test files.
``--api`` names the API's functions, as ``fw.hdl.api.Functions`` does; the API
package is generated into the work directory. Exit status 0 if no test has a counterexample, is vacuous
or is unknown; a test that is not formal is reported and does not fail.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..config import FlowConfig
from . import prove

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fw.hdl.formal", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("design", nargs="+", help="the design's SV files")
    ap.add_argument("--tests", action="append", required=True, metavar="FILE",
                    help="an SVUnit test file (repeatable)")
    ap.add_argument("--api", action="append", default=[], metavar="FN",
                    help="a function of the call API (repeatable)")
    ap.add_argument("--api-name", help="the API's name (default: from the first function)")
    ap.add_argument("--test", action="append", default=[], help="prove only this test")
    ap.add_argument("--solver", default="dv-solve", choices=sorted(prove.SOLVERS))
    ap.add_argument("--timeout", type=float, default=300.0, help="per query, in seconds")
    ap.add_argument("-o", "--workdir", default="formal.d",
                    help="queries, counterexamples (<test>.cex.json) and results.json")
    ap.add_argument("--replay", metavar="DIR",
                    help="write the test files, with each counterexample's values, into DIR "
                         "(a directed run of the same tests; see fw.hdl.formal.replay)")
    ap.add_argument("-I", "--incdir", action="append", default=[])
    ap.add_argument("-D", "--define", action="append", default=[])
    a = ap.parse_args(argv)

    cfg = FlowConfig(incdirs=list(a.incdir))
    for d in a.define:
        k, _, v = d.partition("=")
        cfg.defines[k] = v
    try:
        solver = prove.Solver.named(a.solver, a.timeout)
    except FileNotFoundError as e:
        ap.error(str(e))

    files = list(a.design)
    api = None
    if a.api:
        api, pkg = prove.make_api(a.design, a.api, a.workdir, a.api_name,
                                  FlowConfig(incdirs=list(a.incdir)))
        files.append(pkg)
    files += a.tests
    results = prove.prove_files(files, api=api, tests=a.test or None, solver=solver,
                                workdir=a.workdir, config=cfg)
    prove.write_results(results, Path(a.workdir) / "results.json")
    print(prove.report(results))
    if a.replay:
        from . import replay
        cex = [str(Path(a.workdir) / f"{r.test}.cex.json") for r in results
               if r.status == prove.CEX]
        for f in replay.replay_files(a.tests, cex, a.replay):
            print(f"replay: {f}")
    bad = [r for r in results if r.status not in (prove.PROVEN, prove.NOT_FORMAL)]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
