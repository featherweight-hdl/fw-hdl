"""QoR probe for fw_keyed_table (not a test): the unstaged step at 16, 64 and
256 slots, 12-bit keys and 48-bit values, lowered by XLS at one stage with
the asap7 delay model. Prints, per size: the state bits, the critical path
and the source line that dominates it, and the fewest stages that meet each
of a few clock periods.

    python tests/xls/lib/qor_keyed_table.py [N ...]   # logs in build/qor_keyed_table/
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path[:0] = [str(HERE.parent)]

from fw.hdl.ppa import block_ppa                                         # noqa: E402
from fw.hdl.xls_flow import sv_to_component                              # noqa: E402
from zuspec.be.xls.lower_proc import codegen_flags, lower_component      # noqa: E402
from zuspec.be.xls.printer import format_package                         # noqa: E402
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main        # noqa: E402

PKG = str(HERE / "lib_table_pkg.sv")
PERIODS = (1000, 667, 500)


def probe(n: int, out: Path) -> dict:
    comp = sv_to_component([PKG], f"tbl_q{n}")
    pkg = lower_component(comp)
    d = out / f"n{n}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "in.ir").write_text(format_package(pkg))
    t0 = time.time()
    with open(d / "opt.ir", "w") as fp, open(d / "opt.log", "w") as lg:
        subprocess.run([opt_main(), str(d / "in.ir")], stdout=fp, stderr=lg, check=True)
    flags = ["--generator=pipeline", "--delay_model=asap7", "--reset=rst",
             "--use_system_verilog=true", *codegen_flags(comp, pkg)]

    def codegen(tag, extra):
        with open(d / f"{tag}.log", "w") as lg:
            r = subprocess.run([codegen_main(), str(d / "opt.ir"), *flags, *extra,
                                f"--output_verilog_path={d / tag}.sv",
                                f"--output_schedule_path={d / tag}.sched"],
                               stdout=lg, stderr=subprocess.STDOUT)
        return r.returncode == 0

    codegen("s1", ["--pipeline_stages=1"])
    ppa = block_ppa(f"tbl_q{n}", (d / "opt.ir").read_text(), (d / "s1.sched").read_text())
    meets = {}
    for p in PERIODS:
        ok = codegen(f"p{p}", [f"--clock_period_ps={p}"])
        meets[p] = (block_ppa("x", (d / "opt.ir").read_text(),
                              (d / f"p{p}.sched").read_text()).stages if ok else None)
    state = sum(st.type.flat_bit_count() for p in pkg.procs for st in p.state)
    return dict(n=n, state=state, crit=ppa.crit_ps, src=ppa.crit_src.split("/")[-1],
                src_ps=ppa.crit_src_ps, meets=meets, secs=round(time.time() - t0))


def main(argv):
    sizes = [int(a) for a in argv] or [16, 64, 256]
    out = REPO / "build" / "qor_keyed_table"
    print("| N | state bits | 1-stage crit (ps) | dominant line | "
          + " | ".join(f"stages @ {p} ps" for p in PERIODS) + " | secs |")
    print("|---|---|---|---|" + "---|" * len(PERIODS) + "---|")
    for n in sizes:
        r = probe(n, out)
        cells = " | ".join(str(r["meets"][p]) if r["meets"][p] else "fails" for p in PERIODS)
        print(f"| {n} | {r['state']} | {r['crit']} | {r['src']} ({r['src_ps']} ps) | "
              f"{cells} | {r['secs']} |", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
