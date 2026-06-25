"""MMIO-driven FSM recognition and run-body lowering (F-A1 / F-A2).

An *MMIO-driven FSM* is a runnable ``fw_component`` that uses a memory-mapped
register block (a ``fw_reg_block`` subclass member): it sleeps on a watch-set and
drives the block's hardware-owned fields.  ``reg_device`` / ``mmio_fsm`` are the
canonical shape (a DMA channel, a UART, or a SPI controller is the same shape with
more registers and real control flow)::

    forever begin
      m_set.wait_change(which);                  // -> wait_until(set_changed)
      m_regs.status.update('{flag:1, ...}, ...); // -> hwif we/next pulse (Mealy)
    end

This module recognizes that component (F-A1: attach its ``RegBlock`` + ``RegUsage``)
and synthesizes the **FSM SPL** plus a **wiring spec** the structural top assembly
(F-A4) consumes (F-A2):

  - ``set.wait_change(which)`` -> an awaited ``wait_until(set_changed)`` beat, with
    an injected ``<set>_changed`` *input* pin wired from the regblock's change
    pulse;
  - ``reg.update(v, mask)``    -> per hardware-writable targeted field, drives to
    injected ``hwif_in_<reg>__<f>_next`` / ``_we`` *output* pins (tagged Mealy so
    the lowering emits a one-cycle ``we`` pulse, D1), wired into the regblock.

Several FSMs may be driven from one register model (e.g. an FSM per DMA channel);
each is recognized independently here, and the design assembler shares the one
regblock among them.

GENERICITY: ``wait_change`` / ``update`` / ``add`` are fw-hdl register-API method
names (allowed library knowledge).  Register *references* resolve structurally via
the shared :func:`resolve_chain_offset` (D4); targeted fields are decided by the
update's value/mask words against the RegMap, never by user field names.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional, Tuple

import zuspec.ir.core as ir
from pyslang import ast

from ..config import FlowConfig
from ..errors import ErrorReporter
from ..regmap import MmioWiring, RegBlock, Register, RegUsage, WirePin
from . import reg_consumer as _consumer
from .astdump import collect_user_classes
from .parser import Parser
from .reg_consumer import resolve_chain_offset
from .reg_mapper import RegMapper


def _safe(name: str) -> str:
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in name)


def _sig(qreg: str, field: str) -> str:
    """hwif signal stem for a field — must match emit/regblock.py exactly."""
    return f"{qreg}__{field}"


def build_mmio_components(files: List[str], config: FlowConfig,
                         reporter: ErrorReporter) -> Dict[str, "MmioComponent"]:
    """Parse *files* and return {name: MmioComponent} for every MMIO-driven FSM
    (F-A1 recognition + F-A2 lowering).  Empty on parse error."""
    parser = Parser(config, reporter)
    if not parser.parse(files):
        return {}
    classes = {c.name: c for c in collect_user_classes(parser.get_root())}
    rm = RegMapper(reporter)
    regmaps = {c.name: rm.build(c, classes)
               for c in classes.values() if rm.is_reg_block_class(c)}
    mapper = MmioMapper(config, reporter)
    return {c.name: mapper.build(c, regmaps, classes)
            for c in classes.values() if mapper.is_mmio_component(c, regmaps)}


@dc.dataclass
class MmioComponent:
    """A recognized MMIO-driven FSM and everything synthesized from it."""
    name: str
    regs_member: str                 # the component's register-block handle (e.g. m_regs)
    block: RegBlock                  # the register model's RegMap (F-A1)
    usage: RegUsage                  # watch-sets / observers / providers (F-A1)
    spl: Optional[ir.DataTypeComponent] = None   # FSM SPL (F-A2)
    wiring: Optional[MmioWiring] = None           # FSM<->regblock spec (F-A2)


class MmioMapper:
    """Recognize and lower MMIO-driven FSM components."""

    def __init__(self, config: FlowConfig, reporter: ErrorReporter):
        self.config = config
        self.reporter = reporter
        self.rm = RegMapper(reporter)

    # -- F-A1: recognition ----------------------------------------------------
    def regs_member(self, cls_sym, regmaps: Dict[str, RegBlock]) -> Optional[str]:
        """Return the name of *cls_sym*'s register-block member (the property whose
        type is a recognized ``fw_reg_block`` subclass), or ``None``."""
        for m in cls_sym:
            if m.kind == ast.SymbolKind.ClassProperty:
                tname = getattr(m.type, "name", None)
                if tname in regmaps:
                    return m.name
        return None

    def is_mmio_component(self, cls_sym, regmaps: Dict[str, RegBlock]) -> bool:
        """A runnable that uses a register block (F-A1 recognition predicate)."""
        return (self._find_run(cls_sym) is not None
                and self.regs_member(cls_sym, regmaps) is not None)

    def build(self, cls_sym, regmaps: Dict[str, RegBlock],
              by_name: Dict[str, object]) -> MmioComponent:
        """Recognize *cls_sym* and synthesize its MmioComponent (block + usage + SPL
        + wiring)."""
        member = self.regs_member(cls_sym, regmaps)
        tname = next(getattr(m.type, "name", None) for m in cls_sym
                     if m.kind == ast.SymbolKind.ClassProperty and m.name == member)
        block = regmaps[tname]
        usage = _consumer._Analyzer(self.rm, regmaps, self.reporter).analyze(cls_sym)
        comp = MmioComponent(name=cls_sym.name, regs_member=member,
                             block=block, usage=usage)
        self._lower_run(cls_sym, comp)        # F-A2
        return comp

    # -- F-A2: run-body lowering ---------------------------------------------
    def _lower_run(self, cls_sym, comp: MmioComponent) -> None:
        run = self._find_run(cls_sym)
        forever = self._find_forever(run.body) if run is not None else None
        if forever is None:
            raise self.reporter.fail(
                f"MMIO FSM {cls_sym.name!r} run() is not a forever loop")

        block = comp.block
        regs_by_off = {off: (q, reg) for (off, q, reg) in block.flat_registers()}

        fields: List[ir.Field] = []
        name2idx: Dict[str, int] = {}

        def add(field: ir.Field, **pragmas) -> int:
            name2idx[field.name] = len(fields)
            if pragmas:
                field.pragmas.update(pragmas)
            fields.append(field)
            return name2idx[field.name]

        def in_pin(name: str) -> ir.FieldInOut:
            return ir.FieldInOut(name=name, datatype=ir.DataTypeInt(bits=1, signed=False),
                                 is_out=False)

        # clock / reset are present on every runnable component
        add(in_pin("clock"), fw_role="clock")
        add(in_pin("reset"), fw_role="reset")

        connections: List[WirePin] = []
        set_pins: Dict[str, int] = {}                # set var name -> set_changed idx
        read_pins: Dict[str, int] = {}               # hwif_out port -> field idx
        loop_body: List[ir.Stmt] = []

        def sref(i: int) -> ir.ExprRefField:
            return ir.ExprRefField(base=ir.TypeExprRefSelf(), index=i)

        def map_cond(cond) -> ir.Expr:
            """Map a run-body condition.  ``m_regs.<reg>.read().<field>`` becomes a
            ``hwif_out_<reg>__<field>`` *input* the regblock drives; ``!`` negates."""
            if cond.kind == ast.ExpressionKind.Conversion:
                return map_cond(cond.operand)
            if cond.kind == ast.ExpressionKind.UnaryOp:
                if cond.op in (ast.UnaryOperator.LogicalNot, ast.UnaryOperator.BitwiseNot):
                    op = (ir.UnaryOp.Not if cond.op == ast.UnaryOperator.LogicalNot
                          else ir.UnaryOp.Invert)
                    return ir.ExprUnary(op=op, operand=map_cond(cond.operand))
            field_read = self._as_field_read(cond)
            if field_read is not None:
                ref_e, fname = field_read
                off = resolve_chain_offset(ref_e, self._root_block(regs_by_off),
                                           self.rm, {})
                if off is None or off not in regs_by_off:
                    raise self.reporter.fail(
                        f"MMIO FSM {cls_sym.name!r}: read() of an unresolved register")
                qreg, reg = regs_by_off[off]
                fld = next((f for f in reg.fields if f.name == fname), None)
                if fld is None:
                    raise self.reporter.fail(
                        f"MMIO FSM {cls_sym.name!r}: register {qreg!r} has no field {fname!r}")
                port = f"hwif_out_{_sig(qreg, fname)}"
                if port not in read_pins:
                    # fw_read: a post-change register readback — the lowering must
                    # sample it the cycle *after* the change (when it has settled).
                    read_pins[port] = add(in_pin_w(port, fld.width), fw_read=True)
                    connections.append(WirePin(pin=port, regblock_port=port,
                                               width=fld.width, direction="in"))
                return sref(read_pins[port])
            raise self.reporter.fail(
                f"MMIO FSM {cls_sym.name!r}: unsupported run condition "
                f"(Phase A supports `<reg>.read().<field>` and its negation)")

        def in_pin_w(name: str, bits: int) -> ir.FieldInOut:
            return ir.FieldInOut(name=name, datatype=ir.DataTypeInt(bits=bits, signed=False),
                                 is_out=False)

        def map_run_stmt(s) -> List[ir.Stmt]:
            """Map one run-body statement to loop-body statements (recursively for
            an ``if``)."""
            if s.kind == ast.StatementKind.VariableDeclaration:
                return []                             # non-synth local (e.g. `which`)
            if s.kind == ast.StatementKind.Conditional:
                if len(s.conditions) != 1:
                    raise self.reporter.fail(
                        f"MMIO FSM {cls_sym.name!r}: unsupported multi-condition if")
                test = map_cond(s.conditions[0].expr)
                body = [x for bs in self.rm._stmts(s.ifTrue) for x in map_run_stmt(bs)]
                orelse = ([x for bs in self.rm._stmts(s.ifFalse) for x in map_run_stmt(bs)]
                          if s.ifFalse is not None else [])
                return [ir.StmtIf(test=test, body=body, orelse=orelse)]
            if s.kind != ast.StatementKind.ExpressionStatement:
                raise self.reporter.fail(
                    f"MMIO FSM {cls_sym.name!r}: unsupported run statement {s.kind.name}")
            e = s.expr
            if e.kind != ast.ExpressionKind.Call:
                raise self.reporter.fail(
                    f"MMIO FSM {cls_sym.name!r}: unsupported run expression {e.kind.name}")
            method = getattr(e, "subroutineName", None)
            if method == "wait_change":
                self._lower_wait(e, set_pins, connections, add, in_pin, sref, loop_body)
                return []                             # the wait beat is appended directly
            if method == "update":
                return self._lower_update(e, regs_by_off, connections, name2idx, add,
                                          sref, cls_sym.name)
            raise self.reporter.fail(
                f"MMIO FSM {cls_sym.name!r}: unsupported run call {method!r}")

        for s in self.rm._stmts(forever.body):
            loop_body.extend(map_run_stmt(s))

        run_fn = ir.Function(
            name="run", is_async=True,
            body=[ir.StmtWhile(test=ir.ExprConstant(value=True),
                               body=loop_body, orelse=[])])
        comp.spl = ir.DataTypeComponent(
            name=cls_sym.name, super=None, fields=fields, proc_processes=[run_fn])
        comp.wiring = MmioWiring(
            component_module=cls_sym.name,
            regblock_module=f"{block.name}_regblock",
            shared=["clock", "reset"],
            connections=connections)

    def _lower_wait(self, e, set_pins, connections, add, in_pin, sref, loop_body) -> None:
        set_name = self._name_of(getattr(e, "thisClass", None))
        if set_name is None:
            raise self.reporter.fail("wait_change() with an unresolved watch-set")
        if set_name not in set_pins:
            port = f"{_safe(set_name)}_changed"
            idx = add(in_pin(port), fw_set=set_name)
            set_pins[set_name] = idx
            connections.append(WirePin(pin=port, regblock_port=port,
                                       width=1, direction="in"))
        cond = sref(set_pins[set_name])
        wait = ir.StmtExpr(expr=ir.ExprAwait(value=ir.ExprCall(
            func=ir.ExprAttribute(value=ir.TypeExprRefSelf(), attr="wait_until"),
            args=[cond], keywords=[])))
        loop_body.append(wait)

    def _lower_update(self, e, regs_by_off, connections, name2idx, add, sref,
                      comp_name) -> List[ir.Stmt]:
        """Lower an ``update(v, mask)`` to per-field Mealy hwif drives, returning the
        drive statements (the caller places them in the wait beat's following-comb,
        possibly inside an ``if``)."""
        off = resolve_chain_offset(getattr(e, "thisClass", None),
                                   self._root_block(regs_by_off), self.rm, {})
        if off is None or off not in regs_by_off:
            raise self.reporter.fail(
                f"MMIO FSM {comp_name!r}: update() on an unresolved register")
        qreg, reg = regs_by_off[off]
        drives: List[ir.Stmt] = []
        for f, val in self._update_drives(e, reg, comp_name):
            stem = _sig(qreg, f.name)
            next_port = f"hwif_in_{stem}_next"
            we_port = f"hwif_in_{stem}_we"
            next_fld = ir.FieldInOut(name=next_port,
                                     datatype=ir.DataTypeInt(bits=f.width, signed=False),
                                     is_out=True)
            we_fld = ir.FieldInOut(name=we_port,
                                   datatype=ir.DataTypeInt(bits=1, signed=False),
                                   is_out=True)
            next_idx = add(next_fld, fw_mealy=True)
            we_idx = add(we_fld, fw_mealy=True)
            drives.append(ir.StmtAssign(targets=[sref(next_idx)],
                                        value=ir.ExprConstant(value=val)))
            drives.append(ir.StmtAssign(targets=[sref(we_idx)],
                                        value=ir.ExprConstant(value=1)))
            connections.append(WirePin(pin=next_port, regblock_port=next_port,
                                       width=f.width, direction="out"))
            connections.append(WirePin(pin=we_port, regblock_port=we_port,
                                       width=1, direction="out"))
        return drives

    @staticmethod
    def _as_field_read(e):
        """If *e* is ``<reg-ref>.read().<field>``, return (reg-ref expr, field name);
        else ``None``."""
        if e.kind != ast.ExpressionKind.MemberAccess:
            return None
        inner = e.value
        if inner.kind == ast.ExpressionKind.Conversion:
            inner = inner.operand
        if inner.kind != ast.ExpressionKind.Call:
            return None
        if getattr(inner, "subroutineName", None) != "read":
            return None
        return getattr(inner, "thisClass", None), e.member.name

    def _update_drives(self, e, reg: Register, comp_name
                       ) -> List[Tuple[object, int]]:
        """Resolve an ``update(v, mask)`` call to [(field, value)] for each
        hardware-writable field the mask selects."""
        layout = [(f.name, f.lsb, f.width) for f in reg.fields]
        W = reg.width
        args = list(getattr(e, "arguments", []) or [])
        value_word = self.rm._eval_value(args[0], layout, W) if args else 0
        mask_word = (self.rm._eval_value(args[1], layout, W)
                     if len(args) > 1 else (1 << W) - 1)
        if value_word is None or mask_word is None:
            raise self.reporter.fail(
                f"MMIO FSM {comp_name!r}: update() value/mask did not constant-fold")
        drives: List[Tuple[object, int]] = []
        for f in reg.fields:
            fmask = ((1 << f.width) - 1) << f.lsb
            if not (mask_word & fmask):
                continue
            if not f.hw_write:
                self.reporter.warning(
                    f"MMIO FSM {comp_name!r}: update() targets non-hardware field "
                    f"{reg.name}.{f.name}; no hwif port — skipped")
                continue
            drives.append((f, (value_word >> f.lsb) & ((1 << f.width) - 1)))
        return drives

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _root_block(regs_by_off) -> RegBlock:
        """A RegBlock view whose top-level registers are the model's flat registers
        — so the shared chain resolver finds ``m_regs.<reg>`` directly."""
        blk = RegBlock(name="_mmio_root")
        for off, (q, reg) in regs_by_off.items():
            blk.registers.append(Register(name=reg.name, offset=off, width=reg.width,
                                          fields=reg.fields))
        return blk

    @staticmethod
    def _name_of(e) -> Optional[str]:
        if e is None:
            return None
        sym = getattr(e, "symbol", None)
        return getattr(sym, "name", None) if sym is not None else None

    @staticmethod
    def _find_run(cls_sym):
        for m in cls_sym:
            if (m.kind == ast.SymbolKind.Subroutine
                    and getattr(m, "name", None) == "run"
                    and getattr(m, "subroutineKind", None) == ast.SubroutineKind.Task
                    and getattr(m, "body", None) is not None):
                return m
        return None

    def _find_forever(self, body):
        for s in self.rm._stmts(body):
            if s.kind == ast.StatementKind.ForeverLoop:
                return s
        return None
