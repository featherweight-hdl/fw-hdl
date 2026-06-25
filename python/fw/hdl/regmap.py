"""RegMap IR — the flattened, elaboration-time representation of a register block.

This is the first lowering step for the register model (register-model-rtl-lowering.md
§1): the OOP register/block object graph is *elaborated* into a flat, static
description — a per-*field* table (fields are the atomic unit), each annotated with
the attributes the RTL emission needs: absolute offset, bit placement, sw/hw/rclr
access, and reset. Virtual dispatch, queues, and the associative offset map of the
SV model do **not** survive into this IR.

The recognizer that populates a ``RegBlock`` from parsed SystemVerilog lives in
``fe/reg_mapper.py``; this module is just the data model plus the ``flatten`` walk
and a human-readable dump used by golden tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class RegField:
    """One field (a slice of a register's packed struct)."""
    name: str
    lsb: int                 # least-significant bit within the register word
    width: int
    sw_write: bool           # software may write these bits (sw_wmask)
    hw_write: bool           # hardware may write these bits (hw_wmask)
    rclr: bool               # cleared as a side effect of a software read (rclr_mask)
    reset: int = 0           # field reset value

    @property
    def msb(self) -> int:
        return self.lsb + self.width - 1

    def access(self) -> str:
        """Classify the field's access policy (datasheet-style)."""
        if not self.sw_write and not self.hw_write:
            return "RESERVED"
        if self.rclr:
            return "ROC"                          # read-to-clear (sticky hw-set)
        if self.sw_write and self.hw_write:
            return "RW/hw"                         # sw + hw both drive (hw wins)
        if self.hw_write:
            return "RO"                            # hw owns, sw reads
        return "RW"                                # sw owns (covers WO at value level)


@dataclass
class Register:
    """One register: a word of state at ``offset`` with a field layout + masks."""
    name: str
    offset: int              # byte offset within the owning block
    width: int               # bus width W
    fields: List[RegField] = field(default_factory=list)
    reset: int = 0
    sw_wmask: int = 0
    hw_wmask: int = 0
    rclr_mask: int = 0
    # masks the recognizer could not constant-fold (logged, not silently dropped)
    unresolved: Tuple[str, ...] = ()


@dataclass
class RegBlock:
    """A register group: registers at local offsets, plus nested sub-blocks."""
    name: str
    registers: List[Register] = field(default_factory=list)
    subblocks: List[Tuple[int, "RegBlock"]] = field(default_factory=list)  # (base, block)
    size: int = 0

    # -- the flat field table (absolute offsets) ---------------------------
    def flatten(self, base: int = 0, prefix: str = "") -> List["FlatField"]:
        out: List[FlatField] = []
        for r in self.registers:
            qname = f"{prefix}{r.name}"
            for f in r.fields:
                out.append(FlatField(
                    abs_offset=base + r.offset, reg=qname, field=f.name,
                    lsb=f.lsb, width=f.width,
                    sw_write=f.sw_write, hw_write=f.hw_write, rclr=f.rclr,
                    reset=f.reset, access=f.access()))
        for boff, blk in self.subblocks:
            out.extend(blk.flatten(base + boff, prefix=f"{prefix}{blk.name}."))
        return out

    def flat_registers(self, base: int = 0, prefix: str = ""
                       ) -> List[Tuple[int, str, "Register"]]:
        """Flatten to [(absolute_offset, qualified_name, Register)], registers of
        this block first, then nested sub-blocks (recursively)."""
        out: List[Tuple[int, str, Register]] = []
        for r in self.registers:
            out.append((base + r.offset, f"{prefix}{r.name}", r))
        # sub-block instances share a class name, so disambiguate by index to keep
        # generated signal names unique.
        for i, (boff, blk) in enumerate(self.subblocks):
            out.extend(blk.flat_registers(base + boff, prefix=f"{prefix}{blk.name}{i}_"))
        return out

    def to_text(self) -> str:
        """Stable, human-readable dump of the flat field table (for golden tests)."""
        lines = [f"regblock {self.name} size=0x{self.size:x}"]
        for ff in self.flatten():
            lines.append(
                f"  0x{ff.abs_offset:04x} {ff.reg}.{ff.field}"
                f" [{ff.lsb+ff.width-1}:{ff.lsb}] {ff.access}"
                f" reset=0x{ff.reset:x}")
        return "\n".join(lines)


@dataclass
class RegUsage:
    """How a consumer (hardware component) uses a register block — recovered from
    the consumer's code (fe/reg_consumer.py) and fed to the emitter so it can lower
    the consumer-facing signals (register-model-rtl-lowering.md §7).

    Offsets are absolute byte offsets into the block being emitted.
    """
    # watch-set name -> member register offsets (the wait_change sets). Each emits
    # a `<set>_changed` output = OR of its members' write strobes.
    change_sets: dict = field(default_factory=dict)
    # registers with a software-write observer (on_write) -> emit a write strobe.
    observers: List[int] = field(default_factory=list)
    # registers with a read provider (on_read) -> RO-reflect (storage elimination,
    # handled in a later milestone; recorded here for completeness).
    providers: List[int] = field(default_factory=list)


@dataclass
class WirePin:
    """One injected FSM pin and the regblock port it connects to (F-A2).

    ``direction`` is from the *FSM component's* point of view: ``"in"`` is driven by
    the regblock (a ``<set>_changed`` pulse or a ``hwif_out`` field readback),
    ``"out"`` is driven by the FSM (a ``hwif_in`` ``_we`` / ``_next`` update strobe).

    ``pin`` is the port on the FSM module; ``regblock_port`` is the port on the
    regblock (also the top-level net name).  They are usually equal, but the set-
    change pin may be qualified per FSM when several FSMs share one register model.
    """
    pin: str                 # port on the generated FSM module
    regblock_port: str       # port on the generated regblock module (and top net)
    width: int
    direction: str           # "in" (regblock -> FSM) | "out" (FSM -> regblock)


@dataclass
class MmioWiring:
    """How one MMIO-driven FSM connects to its register model — the per-FSM slice
    of the structural top assembly spec (F-A4 consumes this).  ``shared`` are
    top-level signals every module takes (clock/reset); ``connections`` are the
    FSM<->regblock nets (set-change pulses + hwif update/readback).  Several FSMs
    may be driven from the same regblock (e.g. an FSM per DMA channel)."""
    component_module: str
    regblock_module: str
    shared: List[str] = field(default_factory=list)        # e.g. ["clock", "reset"]
    connections: List[WirePin] = field(default_factory=list)


@dataclass
class FlatField:
    """A field with its absolute byte offset — one row of the lowering's field table."""
    abs_offset: int
    reg: str
    field: str
    lsb: int
    width: int
    sw_write: bool
    hw_write: bool
    rclr: bool
    reset: int
    access: str
