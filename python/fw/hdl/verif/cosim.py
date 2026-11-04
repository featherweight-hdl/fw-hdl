"""Cosimulate a library class's RTL, any module behind a signal map, against
the class's contract.

A spec (YAML) names the class, its parameters, and one or more *targets*.
A target is a module and a map from the class's ports to the module's
signals. Its RTL is either supplied (``files``) or fw-hdl's own lowering of
a component that wraps the class (``fallback``)::

    class: fw_arbiter
    params: {W: 8, N: 3, POLICY: FW_ARB_RR}
    targets:
      - name: own
        fallback: {files: [cosim_pkg.sv], top: arb3_rr_top, stages: 1}
        ports:
          in[0]: {data: a, valid: a_vld, ready: a_rdy}
          ...
          out:   {data: out, valid: out_vld, ready: out_rdy}
      - name: supplied
        module: my_arb
        files: [my_arb.sv]               # relative to the spec
        params: {LOCK: 1}                # the module's own parameters (optional)
        clock: clk
        reset: {port: rst_n, active_low: true}
        ports: {...}

``fallback`` takes the wrapper's ``files``, its ``top``, the classes to
assign to XLS (``xls``, as in a knob file; a recognized class needs none)
and ``stages``. A port's map has ``data`` and ``valid``, and ``ready``
unless the port is valid-only. The testbench is written from the map and the class's
*driver* (:data:`DRIVERS`): which ports are sources, which are sinks, and how
the environment answers (a credit receiver returns what it is sent). Each
run checks:

- the stream protocol on every output with a ready: once valid, valid and
  data hold until the value is taken;
- the class's per-cycle rules a module must keep whatever its timing (for
  example, credit returns are never stalled);
- the contract (``<class>.yaml`` under ``src/std``): order, conservation, and
  that every value offered leaves.

Timing is free: a module may take more or fewer cycles than the class model,
so nothing is compared cycle for cycle.
"""
from __future__ import annotations

import dataclasses as dc
import os
import random
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import yaml

from fw.hdl.fe.parser import FW_LIB_FILES
from fw.hdl.verif.canon import Event, Rule, check

_SRC = Path(FW_LIB_FILES[0]).resolve().parent


def _sv_hex(v: int, w: int) -> str:
    return f"{w}'h{v:x}"


# --- class drivers --------------------------------------------------------------
@dc.dataclass
class Port:
    name: str             # the class's port, as in the spec ("in[0]")
    width: int
    role: str             # "source" | "sink" | "loop"
    key: Callable[[int], int] = lambda v: 0      # contract key of a value
    data: Callable[[int], int] = lambda v: v     # contract data of a value
    loop: Optional[Tuple[str, int, int]] = None  # (from port, value shift, count)
    always_ready: bool = False                   # a class rule: never stalled


class Driver:
    """What a class's environment is, for its cosim testbench."""
    cls = ""

    def __init__(self, params: Dict):
        self.p = params

    def ports(self) -> List[Port]:
        raise NotImplementedError

    def extra_checks(self, trace: Dict[str, List[Tuple[int, int]]]) -> List[str]:
        return []


def _ib(n: int) -> int:
    return max(1, (n - 1).bit_length())


class ArbiterDriver(Driver):
    """fw_arbiter: ``in[k]`` are sources, ``out`` ({k, value}) a stalling sink."""
    cls = "fw_arbiter"

    def ports(self):
        w, n = self.p["W"], self.p["N"]
        m = (1 << w) - 1
        ps = [Port(f"in[{k}]", w, "source", key=(lambda v, k=k: k)) for k in range(n)]
        ps.append(Port("out", _ib(n) + w, "sink", key=lambda v: v >> w, data=lambda v: v & m))
        return ps


class CreditTxDriver(Driver):
    """fw_credit_tx: ``in[v]`` are sources; ``out`` ({vc, value}) is valid-only;
    the receiver returns ``CHECK`` credits on ``cr`` for each value it is
    sent, some cycles later (:func:`rates`). ``cr`` is never stalled, and
    credits spent and not yet returned never exceed ``CREDITS``."""
    cls = "fw_credit_tx"

    def ports(self):
        w, nvc = self.p["W"], self.p.get("NVC", 1)
        vb, m = _ib(nvc), (1 << w) - 1
        ps = [Port(f"in[{v}]", w, "source", key=(lambda x, v=v: v)) for v in range(nvc)]
        ps.append(Port("cr", vb, "loop", loop=("out", w, self.p.get("CHECK", 1)),
                       always_ready=True))
        ps.append(Port("out", vb + w, "sink", key=lambda v: v >> w, data=lambda v: v & m))
        return ps

    def extra_checks(self, trace):
        check_n, credits = self.p.get("CHECK", 1), self.p["CREDITS"]
        delta: Dict[int, int] = {}
        for c, _ in trace.get("out", []):
            delta[c] = delta.get(c, 0) + check_n
        for c, _ in trace.get("cr", []):
            delta[c] = delta.get(c, 0) - 1
        out, n = [], 0
        for c in sorted(delta):
            n += delta[c]
            if n > credits:
                out.append(f"cycle {c}: {n} credits outstanding, more than CREDITS={credits}")
                break
        return out


class ChannelDriver(Driver):
    """fw_channel: ``put_ex`` is a source and ``get_ex`` a stalling sink. A
    module never holds more than ``DEPTH`` values (none for 0, a wire), and
    for ``DEPTH`` 1 or more a value never leaves in the cycle it came (no
    bypass)."""
    cls = "fw_channel"

    def ports(self):
        w = self.p["W"]
        return [Port("put_ex", w, "source"), Port("get_ex", w, "sink")]

    def extra_checks(self, trace):
        depth, out = self.p["DEPTH"], []
        ins, outs = trace.get("put_ex", []), trace.get("get_ex", [])
        delta: Dict[int, int] = {}
        for c, _ in ins:
            delta[c] = delta.get(c, 0) + 1
        for c, _ in outs:
            delta[c] = delta.get(c, 0) - 1
        n = 0
        for c in sorted(delta):
            n += delta[c]
            if n > depth:
                out.append(f"cycle {c}: {n} values held, more than DEPTH={depth}")
                break
        if depth > 0:
            same = next(((ci, v) for (ci, v), (co, _) in zip(ins, outs) if co <= ci), None)
            if same is not None:
                out.append(f"cycle {same[0]}: value {same[1]:x} left in the cycle it came "
                           f"(a bypass)")
        return out


DRIVERS: Dict[str, type] = {d.cls: d for d in (ArbiterDriver, CreditTxDriver, ChannelDriver)}


# --- specs -----------------------------------------------------------------------
@dc.dataclass
class Target:
    name: str
    ports: Dict[str, Dict[str, str]]
    module: str = ""
    files: List[Path] = dc.field(default_factory=list)
    params: Dict[str, object] = dc.field(default_factory=dict)
    clock: str = "clk"
    reset: str = "rst"
    reset_active_low: bool = False
    fallback: Optional[Dict] = None


@dc.dataclass
class Spec:
    path: Path
    cls: str
    params: Dict
    contract: Dict
    targets: List[Target]


def load(path) -> Spec:
    path = Path(path).resolve()
    d = yaml.safe_load(path.read_text())
    cls = d["class"]
    if cls not in DRIVERS:
        raise ValueError(f"{path}: no cosim driver for class {cls!r} (have {sorted(DRIVERS)})")
    cpath = d.get("contract")
    cpath = (path.parent / cpath) if cpath else next((_SRC / "std").glob(f"**/{cls}.yaml"))
    targets = []
    for t in d["targets"]:
        rst = t.get("reset", {})
        rst = {"port": rst} if isinstance(rst, str) else rst
        fb = t.get("fallback")
        if fb:
            fb = dict(fb, files=[path.parent / f for f in fb["files"]])
        targets.append(Target(name=t["name"], ports=t["ports"], module=t.get("module", ""),
                              files=[path.parent / f for f in t.get("files", [])],
                              params=t.get("params", {}), clock=t.get("clock", "clk"),
                              reset=rst.get("port", "rst"),
                              reset_active_low=bool(rst.get("active_low", False)),
                              fallback=fb))
    return Spec(path, cls, d.get("params", {}), yaml.safe_load(Path(cpath).read_text()),
                targets)


def _fallback(t: Target, workdir: Path) -> Target:
    """The target with fw-hdl's own RTL written to *workdir*."""
    from fw.hdl.spl_flow import spl_to_rtl
    fb = t.fallback
    design = spl_to_rtl([str(f) for f in fb["files"]], fb["top"], list(fb.get("xls", [])),
                        stages=int(fb.get("stages", 1)))
    workdir.mkdir(parents=True, exist_ok=True)
    files = []
    for name, text in design.files.items():
        (workdir / name).write_text(text)
        files.append(workdir / name)
    files += [_SRC / "rtl" / "fw_rv_fifo.sv", _SRC / "rtl" / "fw_valid_check.sv"]
    sig = design.signature
    return dc.replace(t, module=sig.name, files=files, clock=sig.clock, reset=sig.reset,
                      reset_active_low=bool(sig.reset_active_low))


# --- testbench -------------------------------------------------------------------
def _id(port: str) -> str:
    return "p_" + port.replace("[", "_").replace("]", "")


def testbench(t: Target, ports: Sequence[Port], stim: Dict[str, List[int]], seed: int,
              src_pct: int = 75, sink_pct: int = 75, delay: int = 4, idle: int = 100,
              max_cycles: int = 20000) -> str:
    """A testbench for *t*. An idle source offers its next value on
    ``src_pct`` percent of cycles; a sink with a ready is ready on
    ``sink_pct`` percent; a loop source answers 1 to ``delay`` cycles
    after the value it answers. Each
    cycle the testbench drives, waits 1, checks and samples the handshakes,
    then raises the clock; it applies the handshakes' effects 1 after the
    edge. It prints ``T <port> <cycle> <hex>`` per handshake, ``E <cycle>
    <msg>`` per rule broken, and ``X done``."""
    rst_on, rst_off = ("1'b0", "1'b1") if t.reset_active_low else ("1'b1", "1'b0")
    total = sum(len(v) for v in stim.values())
    L = ["module cosim_tb;", "  logic clk = 0;", f"  logic rst = {rst_on};",
         "  int cycle = 0, last = 0;"]
    conns = [f".{t.clock}(clk)", f".{t.reset}(rst)"]
    drive, sample, apply = [], [], []
    for p in ports:
        n, w, m = _id(p.name), p.width, t.ports.get(p.name)
        if m is None:
            raise ValueError(f"target {t.name}: port {p.name} is not mapped")
        rdy = "ready" in m
        # The testbench drives a source's data and valid and a sink's ready.
        if p.role == "sink":
            L += [f"  logic [{w - 1}:0] {n}_d;", f"  logic {n}_v, {n}_r{' = 0' if rdy else ''};"]
        else:
            L += [f"  logic [{w - 1}:0] {n}_d = 0;", f"  logic {n}_v = 0, {n}_r;"]
        L += [f"  bit {n}_t;"]
        conns += [f".{m['data']}({n}_d)", f".{m['valid']}({n}_v)"]
        if rdy:
            conns.append(f".{m['ready']}({n}_r)")
        if p.role == "source":
            vals = stim.get(p.name, [])
            L += [f"  int {n}_n = {len(vals)}, {n}_i = 0;",
                  f"  logic [{w - 1}:0] {n}_q [{max(len(vals), 1)}];", "  initial begin"]
            L += [f"    {n}_q[{i}] = {_sv_hex(v, w)};" for i, v in enumerate(vals)]
            L += ["  end"]
            drive += [f"    if (!{n}_v && {n}_i < {n}_n && $urandom % 100 < {src_pct})"
                      f" begin {n}_v = 1; {n}_d = {n}_q[{n}_i]; end"]
        elif p.role == "loop":
            src, shift, count = p.loop
            size = max(1, total * count + 1)
            L += [f"  int {n}_wr = 0, {n}_rd = 0, {n}_tl = 0, {n}_nx;",
                  f"  int {n}_at [{size}]; logic [{w - 1}:0] {n}_q [{size}];"]
            drive += [f"    if (!{n}_v && {n}_rd < {n}_wr && {n}_at[{n}_rd] <= cycle)"
                      f" begin {n}_v = 1; {n}_d = {n}_q[{n}_rd]; end"]
            s = _id(src)
            # The receiver answers each value it is sent, 1 to delay cycles
            # later, in order.
            sample += [f"    if ({s}_t) for (int j = 0; j < {count}; j++) begin",
                       f"      {n}_nx = cycle + 1 + $urandom % {delay};",
                       f"      {n}_tl = ({n}_tl > {n}_nx) ? {n}_tl : {n}_nx;",
                       f"      {n}_at[{n}_wr] = {n}_tl; {n}_q[{n}_wr] = {w}'({s}_d >> {shift});"
                       f" {n}_wr++;", "    end"]
        else:
            if rdy:
                L += [f"  bit {n}_hold = 0; logic [{w - 1}:0] {n}_last;"]
                drive += [f"    {n}_r = $urandom % 100 < {sink_pct};"]
                sample += [f"    if ({n}_hold && (!{n}_v || {n}_d != {n}_last))"
                           f' $display("E %0d {p.name}: valid or data changed before the'
                           f' value was taken", cycle);',
                           f"    {n}_hold = {n}_v && !{n}_r; {n}_last = {n}_d;"]
            else:
                L += [f"  assign {n}_r = 1'b1;"]
        if p.role != "sink":
            if p.always_ready and rdy:
                sample.insert(0, f"    if ({n}_v && !{n}_r)"
                                 f' $display("E %0d {p.name} stalled", cycle);')
            idx = f"{n}_rd++" if p.role == "loop" else f"{n}_i++"
            apply += [f"    if ({n}_t) begin {n}_v = 0; {idx}; end"]
        # every handshake is printed and sampled before the edge
        sample.insert(0, f"    {n}_t = {n}_v && {n}_r;")
        sample.insert(1, f'    if ({n}_t) begin $display("T {p.name} %0d %0h", cycle, {n}_d);'
                         f" last = cycle; end")
    mparams = ", ".join(f".{k}({v})" for k, v in t.params.items())
    L += [f"  {t.module} {'#(' + mparams + ') ' if mparams else ''}dut({', '.join(conns)});",
          "  initial begin", f"    void'($urandom({seed}));",
          "    repeat (4) begin #5 clk = 1; #5 clk = 0; end", f"    rst = {rst_off};",
          f"    for (cycle = 0; cycle - last < {idle} && cycle < {max_cycles}; cycle++) begin"]
    L += drive + ["    #1;"] + sample + ["    #4 clk = 1;", "    #1;"] + apply + ["    #4 clk = 0;"]
    L += ["    end", '    $display("X done");', "    $finish;", "  end", "endmodule"]
    return "\n".join(L) + "\n"


# --- running ----------------------------------------------------------------------
def find_verilator() -> Optional[str]:
    return os.environ.get("VERILATOR") or shutil.which("verilator")


def _simulate(files: Sequence[Path], workdir: Path, verilator: str) -> List[str]:
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [verilator, "--binary", "--timing", "-j", "0", "-Wno-fatal", "-Wno-lint",
           "-Wno-style", "--assert", "+define+ASSERT_ON", "--top-module", "cosim_tb",
           "-Mdir", str(workdir / "obj"), "-o", "sim", *[str(f) for f in files]]
    log = workdir / "cosim.log"
    with open(log, "w") as fp:
        r = subprocess.run(cmd, stdout=fp, stderr=subprocess.STDOUT, cwd=workdir)
        if r.returncode != 0:
            raise RuntimeError(f"verilator build failed; see {log}")
        r = subprocess.run([str(workdir / "obj" / "sim")], capture_output=True, text=True,
                           cwd=workdir)
        fp.write(r.stdout + r.stderr)
    return (r.stdout + r.stderr).splitlines()


def stimulus(ports: Sequence[Port], seed: int, lo: int = 20,
             hi: int = 40) -> Dict[str, List[int]]:
    """*lo* to *hi* random values for each source."""
    rng = random.Random(seed)
    return {p.name: [rng.randrange(1 << p.width) for _ in range(rng.randint(lo, hi))]
            for p in ports if p.role == "source"}


def rates(seed: int) -> Tuple[int, int, int]:
    """(source %, sink %, loop delay) for a seed: busy and sparse sources, so
    that values arrive both behind and ahead of a stalled grant, and fast and
    slow receivers, so that a credit sender runs both with credit to spare and
    out of it."""
    return ((75, 75, 4), (40, 60, 8), (90, 30, 12), (20, 90, 2))[seed % 4]


def check_run(drv: Driver, contract: Dict, stim: Dict[str, List[int]],
              lines: Sequence[str]) -> List[str]:
    """The rules broken in one run's output (empty when it passes)."""
    errs = [f"cycle {l.split(' ', 2)[1]}: {l.split(' ', 2)[2]}" for l in lines
            if l.startswith("E ")]
    if "X done" not in lines:
        return errs + ["the simulation did not finish"]
    trace: Dict[str, List[Tuple[int, int]]] = {}
    for l in lines:
        f = l.split()
        if len(f) == 4 and f[0] == "T":
            trace.setdefault(f[1], []).append((int(f[2]), int(f[3], 16)))
    ports = drv.ports()
    for p in ports:
        if p.role == "source" and len(trace.get(p.name, [])) != len(stim[p.name]):
            errs.append(f"{p.name}: {len(trace.get(p.name, []))} of {len(stim[p.name])}"
                        " values taken")
    ev, ids = [], {}
    for p in ports:
        if p.role == "loop":
            continue
        for c, v in trace.get(p.name, []):
            k = p.key(v)
            i = ids.get((p.role, k), 0)
            ids[(p.role, k)] = i + 1
            ev.append(Event(p.name, "in" if p.role == "source" else "out", c,
                            (k << 20) | i, key=k, data=p.data(v)))
    ev.sort(key=lambda e: (e.cyc, e.ev != "in"))
    errs += check(ev, Rule.from_dict(contract.get("order", {})))
    # Every value taken leaves (the run ends only after the module is idle).
    n_in = sum(1 for e in ev if e.ev == "in")
    n_out = sum(1 for e in ev if e.ev == "out")
    if n_in != n_out:
        errs.append(f"{n_in} values in, {n_out} out")
    errs += drv.extra_checks(trace)
    return errs


def run(spec: Spec, workdir, seeds: Sequence[int] = (1, 2, 3),
        targets: Optional[Sequence[str]] = None,
        verilator: Optional[str] = None) -> Dict[str, List[str]]:
    """Run each target (or those named) for each seed. Returns
    ``{"<target>/<seed>": [rule broken, ...]}``; all empty means pass."""
    verilator = verilator or find_verilator()
    if not verilator:
        raise RuntimeError("no Verilator: set VERILATOR or put verilator on PATH")
    drv = DRIVERS[spec.cls](spec.params)
    ports = drv.ports()
    workdir = Path(workdir).resolve()
    out = {}
    for t in spec.targets:
        if targets and t.name not in targets:
            continue
        tw = workdir / t.name
        if t.fallback:
            t = _fallback(t, tw / "rtl")
        for seed in seeds:
            stim = stimulus(ports, seed)
            d = tw / f"seed{seed}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "cosim_tb.sv").write_text(testbench(t, ports, stim, seed, *rates(seed)))
            lines = _simulate(list(t.files) + [d / "cosim_tb.sv"], d, verilator)
            out[f"{t.name}/{seed}"] = check_run(drv, spec.contract, stim, lines)
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m fw.hdl.verif.cosim",
                                 description="Cosimulate RTL against a library class's contract.")
    ap.add_argument("spec", nargs="+")
    ap.add_argument("--target", action="append", help="run only this target (repeatable)")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--workdir", default="build/cosim")
    ap.add_argument("--verilator")
    a = ap.parse_args(argv)
    bad = 0
    for s in a.spec:
        spec = load(s)
        res = run(spec, Path(a.workdir) / spec.path.stem, range(1, a.seeds + 1), a.target,
                  a.verilator)
        for k, errs in res.items():
            print(f"{'PASS' if not errs else 'FAIL'} {spec.cls} {k}")
            for e in errs[:10]:
                print(f"    {e}")
            bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
