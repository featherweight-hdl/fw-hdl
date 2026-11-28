"""T7 (docs/design/xtor-shell-plan.md, D9): emits wb_initiator and
wb_target with cocotb bridges (scripts/emit_xtor.py ... cocotb), builds
wb_cocotb_tb.sv (the two cores, no interface or shell) under Verilator
with cocotb, and runs test_wb_cocotb.py plain, +rand, +mut_mem (must
fail) and +no_set (the target's run() must raise). Prints each run's
"== <case>" and its "R ..." line. Run under direnv; output under
$OUT (default rundir/cocotb).

Usage: run_cocotb.py [case ...]   (plain, +rand, +mut_mem, +no_set)
WAIT=edge uses the bridges that sample at every edge (default: event).
"""
import os
import subprocess
import sys
from pathlib import Path

from cocotb_tools.runner import get_runner

here = Path(__file__).resolve().parent
ex = here.parent
out = Path(os.environ.get("OUT", ex / "rundir" / "cocotb")).resolve()
out.mkdir(parents=True, exist_ok=True)

flavor = "cocotb-edge" if os.environ.get("WAIT") == "edge" else "cocotb"
srcs, gens = [], []
for w in ("init", "tgt"):
    g = out / f"gen_{w}"
    with open(out / f"emit_{w}.log", "w") as log:
        r = subprocess.run([sys.executable, str(ex / "scripts" / "emit_xtor.py"), w, str(g),
                            flavor], stdout=subprocess.PIPE, stderr=log, text=True)
    if r.returncode:
        sys.exit((out / f"emit_{w}.log").read_text()[-4000:])
    fl = Path(r.stdout.strip())
    # the core and its types package; not the unused top
    srcs += [l for l in fl.read_text().split() if not l.endswith("_lowered.sv")]
    gens.append(str(g))

runner = get_runner("verilator")
build_log = out / "build.log"
try:
    runner.build(sources=srcs + [str(here / "wb_cocotb_tb.sv")],
                 hdl_toplevel="wb_cocotb_tb", build_dir=str(out / "sim_build"),
                 build_args=["-Wno-fatal", "-Wno-lint", "-Wno-style"],
                 always=True, log_file=str(build_log))
except Exception:
    sys.exit(build_log.read_text()[-4000:] if build_log.exists() else "build failed")

sys.path[:0] = [str(here)] + gens     # the runner passes sys.path as PYTHONPATH
for case in sys.argv[1:] or ["plain", "+rand", "+mut_mem", "+no_set"]:
    log = out / f"run_{case.lstrip('+')}.log"
    print(f"== {case}")
    try:
        runner.test(hdl_toplevel="wb_cocotb_tb", test_module="test_wb_cocotb",
                    build_dir=str(out / "sim_build"), test_dir=str(out),
                    plusargs=[] if case == "plain" else [case], log_file=str(log),
                    results_xml=str(out / f"results_{case.lstrip('+')}.xml"))
    except Exception as e:
        print(f"run failed: {e}")
    lines = [l for l in log.read_text().splitlines() if l.startswith("R ")]
    print("\n".join(lines) if lines else f"(no result; see {log})")
