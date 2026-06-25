"""End-to-end synthesis of an MMIO register-model design (F-A5).

Ties the Phase-A pieces together: parse the MMIO SV (F-A1/F-A2 → ``fe/mmio``),
lower each FSM's SPL to RTL (F-A3 → the shared ``zuspec.synth`` lowering with the
Mealy hwif pulse), emit the regblock core (``emit/regblock``), and assemble the
structural top in IR (F-A4 → ``emit/structural``).

One register model can drive **several** FSMs (e.g. an FSM per DMA channel): the
regblock is emitted once with the *union* of the FSMs' usages, and the top wires
each FSM to it.  When two FSMs name a watch-set the same, the change-set port is
qualified per FSM instance so the regblock ports stay unique.

Produces the SystemVerilog artifacts — ``{regblock.sv, <fsm>.sv…, top.sv}`` —
entirely from SV, with no hand-written SPL.
"""
from __future__ import annotations

import dataclasses as dc
from collections import Counter
from typing import Dict, List, Optional, Tuple

from . import ir_build as _b
from .config import FlowConfig
from .emit.be_sv import emit_sv
from .emit.regblock import emit_regblock
from .emit.structural import build_top_component
from .errors import ErrorReporter
from .fe.mmio import MmioComponent, build_mmio_components
from .lower.spl2rtl import lower_component
from .regmap import MmioWiring, RegUsage, WirePin


def _safe(name: str) -> str:
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in name)


@dc.dataclass
class MmioDesign:
    """The generated artifacts for one register model and the FSM(s) it drives."""
    regblock_module: str
    regblock_sv: str
    top_module: str
    top_sv: str
    fsms: List[Tuple[str, str]]      # (module_name, sv) per distinct FSM module

    def files(self) -> dict:
        """{filename: text} (regblock first — the others instantiate it)."""
        out = {f"{self.regblock_module}.sv": self.regblock_sv}
        for module, sv in self.fsms:
            out[f"{module}.sv"] = sv
        out[f"{self.top_module}.sv"] = self.top_sv
        return out


def synth_mmio_design(files: List[str], config: FlowConfig,
                      reporter: ErrorReporter, *,
                      components: Optional[List[str]] = None,
                      top_name: Optional[str] = None,
                      formal: bool = False) -> Optional[MmioDesign]:
    """Synthesize the {regblock, FSM(s), top} design for the MMIO components in
    *files*.  By default every recognized FSM is included (they must share one
    register model); *components* selects a subset.  ``None`` on error."""
    models = build_mmio_components(files, config, reporter)
    if reporter.has_errors():
        return None
    if not models:
        reporter.error("no MMIO component (fw_component using a register block) found")
        return None

    selected = _select(models, components, reporter)
    if selected is None:
        return None
    blocks = {m.block.name for m in selected}
    if len(blocks) != 1:
        reporter.error(f"selected FSMs use different register models {sorted(blocks)}; "
                       "pass components=[...] to pick those sharing one")
        return None
    block = selected[0].block

    union, fsms = _assemble_union(selected)

    regblock_sv = emit_regblock(block, usage=union, formal=formal)

    fsm_arts: List[Tuple[str, str]] = []
    seen_modules = set()
    for _inst, comp, _wiring in fsms:
        if comp.name in seen_modules:
            continue                              # same FSM class instantiated twice
        seen_modules.add(comp.name)
        rtl = lower_component(comp.spl, config, reporter)
        if rtl is None:
            return None
        fsm_arts.append((comp.name, emit_sv(_b.context([rtl]))))

    top_module = top_name or f"{block.name}_top"
    top = build_top_component(block, union, [(inst, w) for (inst, _c, w) in fsms],
                              top_name=top_module)
    top_sv = emit_sv(_b.context([top]))

    return MmioDesign(
        regblock_module=fsms[0][2].regblock_module,
        regblock_sv=regblock_sv,
        top_module=top_module, top_sv=top_sv,
        fsms=fsm_arts)


def _select(models, components, reporter) -> Optional[List[MmioComponent]]:
    if components is None:
        return list(models.values())
    missing = [c for c in components if c not in models]
    if missing:
        reporter.error(f"MMIO component(s) {missing} not found (have: {sorted(models)})")
        return None
    return [models[c] for c in components]


def _assemble_union(selected: List[MmioComponent]
                    ) -> Tuple[RegUsage, List[Tuple[str, MmioComponent, MmioWiring]]]:
    """Build the regblock's union RegUsage and per-FSM wirings, qualifying any
    watch-set name shared by multiple FSMs so the regblock ports stay unique."""
    set_name_uses = Counter(s for m in selected for s in m.usage.change_sets)

    union = RegUsage()
    fsms: List[Tuple[str, MmioComponent, MmioWiring]] = []
    for m in selected:
        inst = f"u_{m.name}"
        port_remap: Dict[str, str] = {}          # original set port -> qualified
        for sname, offs in m.usage.change_sets.items():
            qname = f"{inst}__{sname}" if set_name_uses[sname] > 1 else sname
            union.change_sets[qname] = list(offs)
            port_remap[f"{_safe(sname)}_changed"] = f"{_safe(qname)}_changed"
        union.observers += m.usage.observers
        union.providers += m.usage.providers

        conns = [WirePin(pin=c.pin,
                         regblock_port=port_remap.get(c.regblock_port, c.regblock_port),
                         width=c.width, direction=c.direction)
                 for c in m.wiring.connections]
        fsms.append((inst, m, MmioWiring(
            component_module=m.wiring.component_module,
            regblock_module=m.wiring.regblock_module,
            shared=list(m.wiring.shared), connections=conns)))

    union.observers = sorted(set(union.observers))
    union.providers = sorted(set(union.providers))
    return union, fsms
