"""QoR probe for library classes lowered as mapped steps (not a test), with
XLS at one stage and the asap7 delay model:

* table: fw_keyed_table at 16, 64 and 256 slots, 12-bit keys and 48-bit
  values (lib_table_pkg's tbl_q<N>);
* pool: fw_token_pool at 64 and 256 tokens with a 32-bit value
  (lib_pool_pkg's pool_q<N>).

Prints, per size: the state bits, the critical path and the source line
that dominates it, and the fewest stages that meet each of a few clock
periods.

    python tests/xls/lib/qor_lib.py table|pool [N ...]   # logs in build/qor_<kind>/
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

# kind: (package file, typedef prefix, default sizes)
KINDS = {"table": ("lib_table_pkg.sv", "tbl_q", [16, 64, 256]),
         "pool": ("lib_pool_pkg.sv", "pool_q", [64, 256])}
PERIODS = (1000, 667, 500)


def probe(kind: str, n: int, out: Path) -> dict:
    pkg_file, prefix, _ = KINDS[kind]
    cls = f"{prefix}{n}"
    comp = sv_to_component([str(HERE / pkg_file)], cls)
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
    ppa = block_ppa(cls, (d / "opt.ir").read_text(), (d / "s1.sched").read_text())
    meets = {}
    for p in PERIODS:
        ok = codegen(f"p{p}", [f"--clock_period_ps={p}"])
        meets[p] = (block_ppa("x", (d / "opt.ir").read_text(),
                              (d / f"p{p}.sched").read_text()).stages if ok else None)
    state = sum(st.type.flat_bit_count() for p in pkg.procs for st in p.state)
    return dict(n=n, state=state, crit=ppa.crit_ps, src=ppa.crit_src.split("/")[-1],
                src_ps=ppa.crit_src_ps, meets=meets, secs=round(time.time() - t0))


def main(argv):
    if not argv or argv[0] not in KINDS:
        sys.exit(f"usage: qor_lib.py {'|'.join(KINDS)} [N ...]")
    kind = argv[0]
    sizes = [int(a) for a in argv[1:]] or KINDS[kind][2]
    out = REPO / "build" / f"qor_{kind}"
    print("| N | state bits | 1-stage crit (ps) | dominant line | "
          + " | ".join(f"stages @ {p} ps" for p in PERIODS) + " | secs |")
    print("|---|---|---|---|" + "---|" * len(PERIODS) + "---|")
    for n in sizes:
        r = probe(kind, n, out)
        cells = " | ".join(str(r["meets"][p]) if r["meets"][p] else "fails" for p in PERIODS)
        print(f"| {n} | {r['state']} | {r['crit']} | {r['src']} ({r['src_ps']} ps) | "
              f"{cells} | {r['secs']} |", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
