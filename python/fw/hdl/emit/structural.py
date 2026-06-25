"""Structural top assembly via IR (F-A4 / Decision D2: the IR route).

Builds the top module that wires one register model (regblock) to the MMIO-driven
FSM(s) it drives, as a :class:`zuspec.ir.core.DataTypeComponent` carrying
``module_instances`` (the structural node added to ir-core) — *not* a text emitter.
The same be-sv back end that renders the FSMs renders the top, so structural
assembly lives in the IR where other back ends (zuspec-be-sw, …) can reuse it.

Several FSMs may share one register model (e.g. an FSM per DMA channel): the
regblock is instantiated once and each FSM is wired to it by its own
:class:`MmioWiring`.  Net names are the regblock port names (unique across FSMs —
the design assembler qualifies any colliding set-change ports beforehand).

The top:
  - exposes ``clock``/``reset`` and the regblock's software **bus**
    (``s_addr``/``s_wr``/``s_wdata``/``s_rd``/``s_rdata``) as module ports;
  - declares the FSM<->regblock nets (``<set>_changed`` pulses and ``hwif`` update
    strobes) plus the regblock's ``hwif_out_*`` readback nets;
  - instantiates the regblock (text-emitted module) and each FSM (IR-emitted),
    connecting every port.
"""
from __future__ import annotations

from typing import List, Sequence, Tuple

import zuspec.ir.core as ir

from ..regmap import MmioWiring, RegBlock, RegUsage
from .regblock import regblock_ports


# the bus + clock/reset ports the top exposes (the software-facing surface)
_BUS = ("clock", "reset", "s_addr", "s_wr", "s_wdata", "s_rd", "s_rdata")


def build_top_component(block: RegBlock, usage: RegUsage,
                        fsms: Sequence[Tuple[str, MmioWiring]], *,
                        top_name: str,
                        regblock_inst: str = "u_regs") -> ir.DataTypeComponent:
    """Assemble the structural top as a ``DataTypeComponent``.

    *usage* is the **union** RegUsage of all FSMs (so the regblock exposes every
    change-set / observer).  *fsms* is ``[(instance_name, MmioWiring)]`` — one
    entry per FSM driven from this register model.  Every regblock port is
    connected: the bus + clock/reset to top ports, the FSM<->regblock nets per the
    wiring, and the readback ``hwif_out_*`` outputs to (unused) nets — so the top
    lints with no missing/empty pins."""
    ports = regblock_ports(block, usage)

    # every FSM<->regblock net, keyed by the regblock port (== net name)
    wired = {}
    for _inst, w in fsms:
        for c in w.connections:
            wired[c.regblock_port] = c

    fields: List[ir.Field] = []

    def add(f: ir.Field) -> None:
        fields.append(f)

    # top ports: clock/reset + the regblock software bus (widths from the regblock)
    by_name = {p.name: p for p in ports}
    for n in _BUS:
        p = by_name[n]
        add(ir.FieldInOut(name=n, datatype=ir.DataTypeInt(bits=p.width, signed=False),
                          is_out=(p.direction == "out")))

    # internal nets: every non-bus regblock port (FSM connections + readback
    # hwif_out_*).  Readbacks aren't consumed here (software reads them over the
    # bus) — driven-but-unused, lint-clean under -Wno-UNUSEDSIGNAL.
    for p in ports:
        if p.name in _BUS:
            continue
        add(ir.Field(name=p.name, datatype=ir.DataTypeInt(bits=p.width, signed=False)))

    # regblock instance: connect EVERY port to the same-named top port / net
    rb_conns = [ir.PortConnection(port=p.name, signal=p.name) for p in ports]
    instances = [ir.ModuleInstance(module=_regblock_module(fsms, block),
                                    name=regblock_inst, connections=rb_conns)]

    # one instance per FSM: clock/reset + each pin -> its regblock-port net
    for inst, w in fsms:
        conns = [ir.PortConnection(port="clock", signal="clock"),
                 ir.PortConnection(port="reset", signal="reset")]
        conns += [ir.PortConnection(port=c.pin, signal=c.regblock_port)
                  for c in w.connections]
        instances.append(ir.ModuleInstance(module=w.component_module, name=inst,
                                            connections=conns))

    return ir.DataTypeComponent(name=top_name, super=None, fields=fields,
                                module_instances=instances)


def _regblock_module(fsms, block: RegBlock) -> str:
    if fsms:
        return fsms[0][1].regblock_module
    return f"{block.name}_regblock"
