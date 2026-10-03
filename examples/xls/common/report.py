#!/usr/bin/env python3
"""Write RESULTS.md and results.json for the XLS examples (xls-examples.md §8).

Reads what a run left in the run directory -- nothing is rerun -- so run the
examples first (`dfm run tests`, `dfm run <example>.all`). A missing result
is shown as `-`.

    python3 common/report.py [rundir] [out_dir]

Two tables:

* **QoR**, per example and path (SV, DSLX): optimized XLS IR nodes, pipeline
  latency, Yosys cells per target, and the equivalence verdict.
* **Integration**, per example and test level: the test file's sha256, tests
  passed of tests run, the simulation time of the last pass, wall times, and
  the lines of glue the user wrote to run the test at that level.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# example -> (directory, its unit-test file, path label)
EXAMPLES = [
    ("crc32", "crc32", "crc32_unit_test.sv"),
    ("adler32", "adler32", "adler32_unit_test.sv"),
    ("lfsr", "lfsr", "lfsr_unit_test.sv"),
    ("lfsr_proc", "lfsr", "lfsr_proc_unit_test.sv"),
    ("gcd", "gcd", "gcd_unit_test.sv"),
    ("prefix_sum", "prefix_sum", "prefix_sum_unit_test.sv"),
    ("fir_dot", "fir_dot", "fir_dot_unit_test.sv"),
    ("idct_chen", "idct_chen", "idct_chen_unit_test.sv"),
    ("sha256", "sha256", "sha256_unit_test.sv"),
    ("rle", "rle", "rle_unit_test.sv"),
    ("rle_loop", "rle", "rle_loop_unit_test.sv"),
    ("aes", "aes", "aes_unit_test.sv"),
    ("aes_ctr", "aes_ctr", "aes_ctr_unit_test.sv"),
]
LEVELS = ["model", "rtl", "gates", "gates-ice40", "gates-ecp5", "dslx-rtl", "dslx-gates",
          "rtl-p1000", "rtl-p2000", "rtl-p4000"]
TARGETS = ["generic", "ice40", "ecp5"]

# Headline cell classes per target.
CELLS = {
    "ice40": {"LUT4": ["SB_LUT4"], "FF": ["SB_DFF"], "CARRY": ["SB_CARRY"],
              "BRAM": ["SB_RAM40_4K"], "DSP": ["SB_MAC16"]},
    "ecp5": {"LUT4": ["LUT4"], "FF": ["TRELLIS_FF"], "CCU2C": ["CCU2C"],
             "BRAM": ["DP16KD"], "MULT18": ["MULT18X18D"]},
}


def _read(path: str) -> str:
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def sloc(paths: List[str]) -> int:
    n = 0
    for p in paths:
        for line in _read(p).splitlines():
            s = line.strip()
            if s and not s.startswith("//"):
                n += 1
    return n


def ir_nodes(path: str) -> int:
    return sum(1 for l in _read(path).splitlines()
               if l.startswith("  ") and re.match(r"^\s+(ret\s+)?[\w.]+: ", l))


def latency(path: str) -> Optional[int]:
    m = re.search(r"^\s+latency: (\d+)", _read(path), re.M)
    return int(m.group(1)) if m else None


def stats(path: str) -> Dict[str, int]:
    """cell type -> count, summed over the modules of a stat.json."""
    try:
        with open(path) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    out: Dict[str, int] = {"_cells": 0}
    for m in d.get("modules", {}).values():
        out["_cells"] += int(m.get("num_cells", 0))
        for k, v in (m.get("num_cells_by_type") or {}).items():
            out[k.lstrip("$")] = out.get(k.lstrip("$"), 0) + int(v)
    return out


def cell_summary(target: str, st: Dict[str, int]) -> str:
    if not st:
        return "-"
    if target not in CELLS:
        return str(st["_cells"])
    parts = []
    for label, prefixes in CELLS[target].items():
        n = sum(v for k, v in st.items() if any(k.startswith(p) for p in prefixes))
        if n:
            parts.append(f"{n} {label}")
    return f"{st['_cells']} ({', '.join(parts)})" if parts else str(st["_cells"])


def qor(rundir: str, ex: str) -> Dict:
    row = {"example": ex}
    # An example whose test blocks differ from the DSLX path's (rle) has
    # like-for-like rtl-qor/synth-qor tasks; the table uses those.
    sv_rtl, sv_syn = ("rtl-qor", "synth-qor") if os.path.isdir(
        os.path.join(rundir, f"xls_examples.{ex}.rtl-qor")) else ("rtl", "synth")
    for path, rtl, syn in (("sv", sv_rtl, sv_syn), ("dslx", "dslx-rtl", "dslx-synth")):
        d = os.path.join(rundir, f"xls_examples.{ex}.{rtl}")
        irs = sorted(glob.glob(os.path.join(d, "*.opt.ir")))
        sigs = sorted(glob.glob(os.path.join(d, "*.sig.textproto")))
        row[path] = {
            "ir_nodes": sum(ir_nodes(p) for p in irs) if irs else None,
            "latency": max((latency(s) or 0) for s in sigs) if sigs else None,
            "cells": {t: stats(os.path.join(rundir, f"xls_examples.{ex}.{syn}.{t}", "stat.json"))
                      for t in TARGETS},
        }
    eq = os.path.join(rundir, f"xls_examples.{ex}.equiv", "equiv.json")
    try:
        with open(eq) as f:
            e = json.load(f)
        pairs = e.get("pairs", [e])
        row["equiv"] = {"verdict": e["verdict"],
                        "pairs": [(os.path.basename(p["lhs"]), p["verdict"],
                                   p.get("method", "solver")) for p in pairs]}
    except (OSError, ValueError, KeyError):
        row["equiv"] = None
    return row


def integration(rundir: str, ex: str, exdir: str, test: str) -> List[Dict]:
    tfile = os.path.join(HERE, exdir, test)
    sha = hashlib.sha256(open(tfile, "rb").read()).hexdigest() if os.path.isfile(tfile) else None
    glue = sloc(sorted(glob.glob(os.path.join(HERE, exdir, "dslx_glue", "*.sv"))))
    rows = []
    for lvl in LEVELS:
        run = os.path.join(rundir, f"xls_examples.run.{ex}.{lvl}")
        log = _read(os.path.join(run, "sim.log"))
        if not log:
            continue
        passed = re.findall(r"\[(\d+)\]\[[\w.]+\]: \w+::PASSED", log)
        failed = re.findall(r"\]: \w+::FAILED", log)
        summary = re.search(r"\]\[testrunner\]: (PASSED|FAILED)", log)
        wall = re.search(r"walltime_s=([\d.]+)", _read(os.path.join(run, "sim.time")))
        img = os.path.join(rundir, f"xls_examples.img.{ex}.{lvl}")
        # The image build: from build.f, which the task writes just before it
        # runs Verilator, to the linked simv (task data records no durations).
        # Not obj_dir's oldest file: Verilator leaves unchanged outputs alone,
        # so on a rebuild those date from an earlier build.
        build = None
        bf = os.path.join(img, "build.f")
        sv = os.path.join(img, "obj_dir", "simv")
        if os.path.isfile(bf) and os.path.isfile(sv):
            build = round(os.path.getmtime(sv) - os.path.getmtime(bf), 1)
            if build < 0:   # build.f rewritten, image up to date: not measured
                build = None
        rows.append({
            "example": ex, "level": lvl, "test_sha256": sha,
            "passed": len(passed), "run": len(passed) + len(failed),
            "verdict": summary.group(1) if summary else "error",
            "last_pass_simtime": int(passed[-1]) if passed else None,
            "run_wall_s": round(float(wall.group(1)), 3) if wall else None,
            "build_s": build,
            "glue_lines": glue if lvl.startswith("dslx-") else 0,
        })
    return rows


def sweep(rundir: str) -> List[Dict]:
    """sha256 scheduled at several clock periods (xls-examples.md EX-4)."""
    out = []
    for d in sorted(glob.glob(os.path.join(rundir, "xls_examples.sha256.sweep-rtl.*")),
                    key=lambda d: int(d.rsplit(".", 1)[1])):
        period = int(d.rsplit(".", 1)[1])
        sig = os.path.join(d, "sha256_pkg__sha256.sig.textproto")
        st = stats(os.path.join(rundir, f"xls_examples.sha256.sweep-synth.{period}", "stat.json"))
        log = _read(os.path.join(rundir, f"xls_examples.run.sha256.rtl-p{period}", "sim.log"))
        passed = re.findall(r"\]: \w+::PASSED", log)
        failed = re.findall(r"\]: \w+::FAILED", log)
        out.append({"period_ps": period, "latency": latency(sig),
                    "generic_cells": st.get("_cells"),
                    "tests": f"{len(passed)}/{len(passed) + len(failed)}" if log else None})
    return out


def md(q: List[Dict], it: List[Dict], sw: List[Dict]) -> str:
    o = ["# XLS examples: results", "",
         "Generated by `common/report.py` from a run of the examples; refresh it on "
         "purpose (`python3 common/report.py`). `-` means no result in the run directory.",
         "", "## Integration: one test file, every level", "",
         "| example | level | test sha256 | pass | sim time of last pass | run (s) | image build (s) | glue lines |",
         "|---|---|---|---|---|---|---|---|"]
    for r in it:
        o.append(f"| {r['example']} | {r['level']} | `{(r['test_sha256'] or '-')[:12]}` | "
                 f"{r['passed']}/{r['run']} {'' if r['verdict'] == 'PASSED' else r['verdict']} | "
                 f"{r['last_pass_simtime'] if r['last_pass_simtime'] is not None else '-'} | "
                 f"{r['run_wall_s'] if r['run_wall_s'] is not None else '-'} | "
                 f"{r['build_s'] if r['build_s'] is not None else '-'} | {r['glue_lines']} |")
    o += ["", "The sha256 is the same down each example's rows: one unedited file. The "
          "simulation time grows from the model (no clock) to RTL and gates (reset, then "
          "pipeline latency); a level that answers sooner than its latency allows is a "
          "finding (xls-examples.md risk 6). Glue lines are what a user writes by hand to "
          "run the test at that level: none on the fw-hdl path; `crc32/dslx_glue/` on the "
          "DSLX path. lfsr_proc polls, so when it sees a seed depends on the level; its test "
          "syncs on each new seed and checks the values skipped (lfsr/README.md).", "",
          "## QoR: the SV port against the original", "",
          "| example | path | IR nodes | latency | generic | ice40 | ecp5 | equivalence |",
          "|---|---|---|---|---|---|---|---|"]
    for r in q:
        eq = r["equiv"]
        eqs = "-" if not eq else (eq["verdict"] + (
            "" if len(eq["pairs"]) == 1 and eq["pairs"][0][2] == "solver" else
            " (" + ", ".join(f"{v}{' by ' + m if m != 'solver' else ''}"
                             for _, v, m in eq["pairs"]) + ")"))
        for path in ("sv", "dslx"):
            p = r[path]
            o.append(f"| {r['example'] if path == 'sv' else ''} | {path.upper()} | "
                     f"{p['ir_nodes'] if p['ir_nodes'] is not None else '-'} | "
                     f"{p['latency'] if p['latency'] is not None else '-'} | "
                     + " | ".join(cell_summary(t, p["cells"][t]) for t in TARGETS)
                     + f" | {eqs if path == 'sv' else ''} |")
    o += ["", "Cells are Yosys's `stat`, summed over an example's modules. Procs (lfsr_proc, "
          "rle, aes_ctr) have no equivalence check: XLS's checker takes functions only.", ""]
    if sw:
        o += ["## sha256 at three clock periods (asap7 delay model)", "",
              "| clock period (ps) | pipeline latency | generic cells | the same tests |",
              "|---|---|---|---|"]
        for r in sw:
            o.append(f"| {r['period_ps']} | {r['latency'] if r['latency'] is not None else '-'} "
                     f"| {r['generic_cells'] if r['generic_cells'] is not None else '-'} "
                     f"| {r['tests'] or '-'} |")
        o += ["", "One test file passes against every pipeline: the transactor reads each "
              "latency from XLS's signature.", ""]
    return "\n".join(o)


def main(argv: List[str]) -> int:
    rundir = argv[1] if len(argv) > 1 else os.path.join(HERE, "rundir")
    out = argv[2] if len(argv) > 2 else HERE
    q = [qor(rundir, ex) for ex, _, _ in EXAMPLES]
    it = [r for ex, d, t in EXAMPLES for r in integration(rundir, ex, d, t)]
    sw = sweep(rundir)
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump({"qor": q, "integration": it, "sweep": sw}, f, indent=2)
    with open(os.path.join(out, "RESULTS.md"), "w") as f:
        f.write(md(q, it, sw))
    print(f"wrote {os.path.join(out, 'RESULTS.md')}: {len(it)} integration rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
