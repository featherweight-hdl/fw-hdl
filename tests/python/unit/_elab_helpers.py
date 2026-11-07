"""Helpers for tests of the elaborate-then-lower path (fe/elab).

Takes SystemVerilog text (a design top module, with the fw-hdl library), runs it
through parse -> elaborate -> translate -> structure (:func:`translate_sv`) and
then ``zuspec.synth.proc.lower`` (:func:`lower_sv`), and simulates the class
model and the lowered netlist under Verilator on the same testbench
(:func:`sim_class`, :func:`sim_netlist`), so a test can compare them cycle by
cycle.

A testbench instantiates the design top by its module name. The lowered netlist
keeps that name, so one testbench serves both runs. It prints whatever it
compares and ends with the line ``X done``.
"""
from __future__ import annotations

import dataclasses as dc
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from fw.hdl.fe.elab.flow import ElabStages, elab_design
from fw.hdl.fe.parser import FW_LIB_FILES, FW_LIB_INCDIRS

_REPO = Path(__file__).resolve().parents[3]


@dc.dataclass
class Lowered:
    stages: ElabStages
    design: object          # zuspec.synth.proc.ir.Design, as given to lower
    netlist: object         # the optimized netlist
    verilog: str
    report: List[str]


def _write(text: str, workdir: Path, name: str) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    p = workdir / name
    p.write_text(text)
    return p


def translate_sv(text: str, top: str, workdir: Path, *,
                 files: Sequence[os.PathLike] = (),
                 defines: Optional[Dict[str, str]] = None,
                 keep_loops: bool = False) -> ElabStages:
    """Parse ``files`` then ``text`` (written to ``workdir/<top>.sv``) with
    the fw-hdl library, elaborate ``top``, translate and structure."""
    src = _write(text, workdir, f"{top}.sv")
    return elab_design([str(f) for f in files] + [str(src)], top, defines=defines,
                       keep_loops=keep_loops)


def lower_sv(text: str, top: str, workdir: Path, *, files: Sequence[os.PathLike] = (),
             defines: Optional[Dict[str, str]] = None, encoding: str = "binary",
             optimize: bool = True, emit: str = "flat", keep_loops: bool = True,
             schedule: str = "as-written", **lower_opts) -> Lowered:
    """:func:`translate_sv`, then the engine ``schedule``
    (``zuspec.synth.proc.sched``), then lower, as ``lower_design`` does.
    ``lower_opts`` are :class:`zuspec.synth.proc.lower.LowerOptions` fields.
    ``keep_loops=False`` has translate unroll loops itself."""
    from zuspec.synth.proc.emit import emit_verilog
    from zuspec.synth.proc.lower import LowerOptions, lower
    from zuspec.synth.proc.lower import optimize as opt_pass
    from zuspec.synth.proc.structured import emit_structured

    from zuspec.synth.proc import sched

    st = translate_sv(text, top, workdir, files=files, defines=defines, keep_loops=keep_loops)
    nl = lower(sched.schedule(st.design, schedule), LowerOptions(encoding=encoding, **lower_opts))
    if optimize:
        nl = opt_pass(nl)
    report = list(st.notes) + list(st.elab.interp.warnings) + list(nl.report)
    v = emit_structured(nl) if emit == "structured" else emit_verilog(nl)
    return Lowered(stages=st, design=st.design, netlist=nl, verilog=v, report=report)


# -- simulation ---------------------------------------------------------------

class VerilatorError(Exception):
    pass


def verilator() -> Optional[str]:
    ws = _REPO.parent / "verilator" / "bin" / "verilator"     # ivpm workspace
    own = _REPO / "packages" / "verilator" / "bin" / "verilator"
    for p in (ws, own):
        if p.exists():
            return str(p)
    return shutil.which("verilator")


def have_verilator() -> bool:
    return verilator() is not None


def run_verilator(files: Sequence[os.PathLike], top: str, workdir: Path, *,
                  with_lib: bool = True, extra: Sequence[str] = ()) -> List[str]:
    """Build and run ``top``; return the simulation's output lines. The run
    must print ``X done``."""
    workdir.mkdir(parents=True, exist_ok=True)
    cmd = [verilator(), "--binary", "--timing", "-j", "4",
           "-Wno-fatal", "-Wno-lint", "-Wno-style",
           "--top-module", top, "-Mdir", str(workdir / "obj"), "-o", "sim", *extra]
    if with_lib:
        cmd += [f"+incdir+{d}" for d in FW_LIB_INCDIRS] + list(FW_LIB_FILES)
    cmd += [str(f) for f in files]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=workdir)
    (workdir / "build.log").write_text(r.stdout + r.stderr)
    if r.returncode != 0:
        raise VerilatorError(f"verilator build failed (see {workdir / 'build.log'}):\n"
                             f"{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    r = subprocess.run([str(workdir / "obj" / "sim")], capture_output=True, text=True,
                       cwd=workdir)
    out = r.stdout.splitlines() + r.stderr.splitlines()
    (workdir / "sim.log").write_text("\n".join(out) + "\n")
    if "X done" not in out:
        raise VerilatorError(f"simulation did not finish (see {workdir / 'sim.log'}):\n"
                             + "\n".join(out[-40:]))
    return out


def sim_class(text: str, top: str, tb: str, tb_top: str, workdir: Path, *,
              files: Sequence[os.PathLike] = (),
              defines: Optional[Dict[str, str]] = None) -> List[str]:
    """Simulate the class model: the design source, the library and ``tb``."""
    wd = workdir / "class"
    src = _write(text, wd, f"{top}.sv")
    tbf = _write(tb, wd, f"{tb_top}.sv")
    defs = {"FW_TRACE_OFF": "1", **(defines or {})}
    extra = [f"+define+{k}={v}" for k, v in defs.items()]
    return run_verilator([*files, src, tbf], tb_top, wd, extra=extra)


def sim_netlist(low: Lowered, tb: str, tb_top: str, workdir: Path, *,
                files: Sequence[os.PathLike] = ()) -> List[str]:
    """Simulate the lowered netlist on ``tb``. ``files`` supplies the RTL of
    any leaf modules the netlist instantiates (``low.stages.design.leaf_defs``)."""
    wd = workdir / "netlist"
    src = _write(low.verilog, wd, "netlist.v")
    tbf = _write(tb, wd, f"{tb_top}.sv")
    return run_verilator([*files, src, tbf], tb_top, wd, with_lib=False)


# -- one-beat ready/valid transactors -----------------------------------------
# The kit's ready/valid transactors (src/std/rv) don't take the elab path (their
# FIFO is an unpacked array written inside a process). These have the same
# handshake, one beat at a time. rv1_get_x / rv1_put_x bind an fw_get_if /
# fw_put_if port to them, and declare the binding latency-insensitive, so
# untimed code may call through them. Put RV1_SV before the design top in the
# source text.

RV1_SV = r'''
interface rv1_in_if #(type T = bit [7:0]) (input clock, input reset,
        input valid, output bit ready, input T data);
    task automatic recv(output T t);
        ready <= 1'b1;
        @(posedge clock);
        while (!valid) @(posedge clock);
        t = data;
        ready <= 1'b0;
    endtask
endinterface

interface rv1_out_if #(type T = bit [7:0]) (input clock, input reset,
        output bit valid, input ready, output T data);
    task automatic send(input T t);
        data  <= t;
        valid <= 1'b1;
        @(posedge clock);
        while (!ready) @(posedge clock);
        valid <= 1'b0;
    endtask
endinterface

package rv1_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    (* fw_latency_insensitive *)   // ready/valid: any delay
    class rv1_get_x #(type T = bit [7:0]) extends fw_export #(fw_get_if #(T))
            implements fw_get_if #(T);
        virtual rv1_in_if #(T) vif;
        function new(string name, fw_component parent, virtual rv1_in_if #(T) vif);
            super.new(name, parent, this);
            this.vif = vif;
        endfunction
        virtual task get(output T t);
            vif.recv(t);
        endtask
    endclass

    (* fw_latency_insensitive *)   // ready/valid: any delay
    class rv1_put_x #(type T = bit [7:0]) extends fw_export #(fw_put_if #(T))
            implements fw_put_if #(T);
        virtual rv1_out_if #(T) vif;
        function new(string name, fw_component parent, virtual rv1_out_if #(T) vif);
            super.new(name, parent, this);
            this.vif = vif;
        endfunction
        virtual task put(input T t);
            vif.send(t);
        endtask
    endclass
endpackage
'''


def rv1_top(top: str, comp: str, gets: Dict[str, str], puts: Dict[str, str],
            imports: Sequence[str] = ()) -> str:
    """A design top for component class ``comp``: each fw_get_if port in
    ``gets`` and fw_put_if port in ``puts`` ({port: payload type}) on a
    one-beat ready/valid interface, with pins <port>_valid, _ready, _data."""
    pins, insts, decls, binds = [], [], [], []
    for p, t in gets.items():
        pins += [f"input {p}_valid", f"output {p}_ready", f"input {t} {p}_data"]
        insts.append(f"    rv1_in_if #({t}) u_{p} (.clock(clock), .reset(reset), "
                     f".valid({p}_valid), .ready({p}_ready), .data({p}_data));")
        decls.append(f"            rv1_get_x #({t}) x_{p};")
        binds.append(f'            x_{p} = new("{p}_x", this, u_{p}); {p}.connect(x_{p});')
    for p, t in puts.items():
        pins += [f"output {p}_valid", f"input {p}_ready", f"output {t} {p}_data"]
        insts.append(f"    rv1_out_if #({t}) u_{p} (.clock(clock), .reset(reset), "
                     f".valid({p}_valid), .ready({p}_ready), .data({p}_data));")
        decls.append(f"            rv1_put_x #({t}) x_{p};")
        binds.append(f'            x_{p} = new("{p}_x", this, u_{p}); {p}.connect(x_{p});')
    imp = "".join(f"    import {i}::*;\n" for i in imports)
    return (f"module {top} (input clock, input reset,\n    " + ",\n    ".join(pins) + ");\n"
            "    import fw_hdl_pkg::*;\n    import fw_std_pkg::*;\n    import rv1_pkg::*;\n"
            + imp + "\n".join(insts) + "\n"
            f"    class {top}_bind extends fw_component_root #({comp});\n"
            "        function new(string name); super.new(name); endfunction\n"
            "        virtual function void connect();\n"
            + "\n".join(decls) + "\n" + "\n".join(binds) + "\n"
            "            super.connect();\n        endfunction\n    endclass\n"
            f"    fw_root #(.Tbind({top}_bind)) u_root (.clock(clock), .reset(reset));\n"
            "endmodule\n")
