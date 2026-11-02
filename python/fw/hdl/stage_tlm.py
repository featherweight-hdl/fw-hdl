"""Stage-TLM ("V3") classes from an XLS pipeline schedule.

`fw.hdl.xls.StageTLM` reads each block's schedule from its Zuspec IR bundle
(`<module>.zir/`, written by `zuspec.xls.Overlay`: the `sched.*` and `timing.*`
facts on the source's anchors) or, without one, from the
`<module>.schedule.textproto` that `synth.xls.Codegen` writes. For each function of
a function API (`fw.hdl.api.Functions`), emits a class whose `op` task
computes the result at zero time, by calling the SV function itself, and
then waits one `@(posedge clk)` per pipeline register: the input flop, one
per stage boundary and the output flop, as codegen builds the module.
"""
from __future__ import annotations

import dataclasses as dc
import os
from typing import Dict, List

from fw.hdl.fn_api import ApiFn, FnApi


@dc.dataclass
class Schedule:
    function: str
    length: int
    min_clock_period_ps: int
    #: stage -> node names, in schedule order
    stages: Dict[int, List[str]]

    def clks(self, flop_inputs: bool = True, flop_outputs: bool = True) -> int:
        """Clocks per op as the `rtl` view (fw.hdl.api.XlsBinding) measures
        it: one per stage, plus the input and output flops. (The module's
        `latency` is one less: the binding spends a clock driving inputs.)"""
        return self.length + int(flop_inputs) + int(flop_outputs)


def parse_schedules(text: str) -> Dict[str, Schedule]:
    """The schedules of a PackageScheduleProto text file, by function name.
    (A thin wrapper over zuspec-be-xls's reader, which the overlay uses too.)"""
    from zuspec.be.xls.read_schedule import parse_schedules as read
    return {name: Schedule(function=s.function, length=s.length or len(s.stages),
                           min_clock_period_ps=s.min_clock_period_ps or 0, stages=s.stages)
            for name, s in read(text).items()}


def schedule_from_bundle(path: str) -> Schedule:
    """The schedule of the block in IR bundle *path* (`<module>.zir/`), read
    through a ResultStore from the newest overlay that schedules it
    (phase0-plan.md D4). Nodes per stage are the XLS nodes the overlay put on
    anchors (parameters on the block's), in the schedule's order: the same
    Schedule as `parse_schedules` gives, so the same SV (exit criterion 5)."""
    from zuspec.ir.core.results import load_store
    store = load_store(path)
    module = os.path.basename(os.path.normpath(path))
    if module.endswith(".zir"):
        module = module[:-4]
    o = next((o for o in reversed(store.overlays()) if "sched.stage_count" in o.kinds()),
             None)
    if o is None:
        raise ValueError(f"{path}: no overlay with a schedule (sched.stage_count)")
    length = o.column("sched.stage_count")["value"][0]
    period = o.column("timing.clock_period_ps")["value"][0] \
        if "timing.clock_period_ps" in o.kinds() else 0
    stages: Dict[int, List[str]] = {k: [] for k in range(length)}
    if "xls.node_stage" in o.kinds():
        # One entry per node (a merged node sits on several anchors), in the
        # schedule's own order.
        nodes = {v["node"]: v for v in o.column("xls.node_stage")["value"]}
        for v in sorted(nodes.values(), key=lambda v: v.get("order", 0)):
            stages.setdefault(v["stage"], []).append(v["node"])
    return Schedule(function=module, length=length, min_clock_period_ps=period or 0,
                    stages=stages)


def stage_table(s: Schedule) -> str:
    """The node -> stage map, one `<stage> <node>` line per node."""
    lines = [f"# {s.function}: {s.length} stage(s), min_clock_period_ps {s.min_clock_period_ps}"]
    for st in sorted(s.stages):
        lines += [f"{st} {n}" for n in s.stages[st]]
    return "\n".join(lines) + "\n"


def _class_sv(f: ApiFn, s: Schedule, clk_if: str, flop_in: bool, flop_out: bool,
              table: str) -> List[str]:
    args = [f"input {a.decl()}" for a in f.args] + [f"output {f.ret.decl()}"]
    call = ", ".join(a.name for a in f.args)
    lines = [
        f"    // {f.path}: XLS module {f.module}, {s.length} stage(s),",
        f"    // min_clock_period_ps {s.min_clock_period_ps}. Nodes per stage"
        f" (full map: {table}):",
    ]
    for st in sorted(s.stages):
        nodes = s.stages[st]
        head = ", ".join(nodes[:4]) + (", ..." if len(nodes) > 4 else "")
        lines.append(f"    //   stage {st}: {len(nodes)} node(s): {head}")
    lines += [
        f"    class {f.name}_stage_tlm;",
        f"        static const int unsigned STAGES   = {s.length};",
        f"        static const int unsigned IN_FLOP  = {int(flop_in)};",
        f"        static const int unsigned OUT_FLOP = {int(flop_out)};",
        f"        // A clock per stage, plus the input and output flops.",
        f"        static const int unsigned CLKS     = {s.clks(flop_in, flop_out)};",
        f"",
        f"        virtual {clk_if} vif;",
        f"        int unsigned clks_per_op;  // CLKS unless overridden",
        f"        int unsigned m_clks;       // clocks spent in op",
        f"",
        f"        function new(virtual {clk_if} vif, int unsigned clks_per_op = 0);",
        f"            this.vif = vif;",
        f"            this.clks_per_op = (clks_per_op != 0) ? clks_per_op : CLKS;",
        f"        endfunction",
        f"",
        f"        // The result at zero time, then a clock per pipeline register.",
        f"        task op({', '.join(args)});",
        f"            result = {f.path}({call});",
        f"            repeat (clks_per_op) begin",
        f"                @(posedge vif.clk);",
        f"                m_clks++;",
        f"            end",
        f"        endtask",
        f"    endclass",
        f"",
    ]
    return lines


def stage_tlm_sv(api: FnApi, scheds: Dict[str, Schedule], pkg: str, clk_if: str,
                 imports: List[str], flop_inputs: bool = True,
                 flop_outputs: bool = True, task: str = "fw.hdl.xls.StageTLM") -> str:
    lines = [f"// Generated by {task} from the XLS schedule of {api.name}. Do not edit.",
             f"interface {clk_if}(input logic clk);",
             f"endinterface",
             f"",
             f"package {pkg};"]
    lines += [f"    import {i}::*;" for i in imports]
    lines.append("")
    for f in api.functions:
        lines += _class_sv(f, scheds[f.module], clk_if, flop_inputs, flop_outputs,
                           f"{f.module}.stages.txt")
    lines.append("endpackage")
    return "\n".join(lines) + "\n"
