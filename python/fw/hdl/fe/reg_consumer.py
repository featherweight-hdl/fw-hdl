"""Recover how a hardware component *uses* a register block (M7 consumer side).

Scans a consumer component's constructor/``build`` for the fw-hdl register-usage
API calls and resolves each register reference to an absolute offset in the
block's RegMap:

  - ``<set>.add(<reg-ref>)``  -> watch-set membership   (wait_change -> set_changed)
  - ``<reg-ref>.set_rd(...)`` -> read provider          (RO-reflect, recorded)
  - ``<reg-ref>.add_wr(...)`` -> software-write observer (on_write strobe)

GENERICITY: the method names above are fw-hdl's register API (allowed library
knowledge). Register *references* are resolved structurally — a member chain
optionally indexed by a loop variable — never by matching user field names. The
loop is unrolled with the same affine recognizer used by the RegMap builder.
A reference indexed into the (single) sub-block array is assumed to select that
array; multiple sub-block arrays would need property-name capture (logged).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pyslang import ast

from ..config import FlowConfig
from ..errors import ErrorReporter
from ..regmap import RegBlock, RegUsage
from .astdump import collect_user_classes
from .parser import Parser
from .reg_mapper import RegMapper


def resolve_chain_offset(e, root_block: RegBlock, rm: RegMapper, env) -> Optional[int]:
    """Resolve a register reference (member chain, optional array index) to an
    absolute offset in *root_block* (D4: shared by the consumer analysis and the
    run-body lowering so they cannot diverge).

    The reference is resolved *structurally* — the outermost member is the
    register name, an optional element-select is the (loop-bound) sub-block index
    — never by matching user field names.
    """
    rname: Optional[str] = None
    idx_expr = None
    x = e
    while x is not None:
        k = x.kind
        if k == ast.ExpressionKind.Conversion:
            x = x.operand
        elif k == ast.ExpressionKind.MemberAccess:
            if rname is None:
                rname = x.member.name          # outermost member = register
            x = x.value
        elif k == ast.ExpressionKind.ElementSelect:
            idx_expr = x.selector              # array index (the loop var)
            x = x.value
        else:
            break                              # reached the root handle
    if rname is None:
        return None
    if idx_expr is not None:
        i = rm._eval_int(idx_expr, env)
        if i is None or i >= len(root_block.subblocks):
            return None
        base, sub = root_block.subblocks[i]
        reg = next((r for r in sub.registers if r.name == rname), None)
        return base + reg.offset if reg is not None else None
    reg = next((r for r in root_block.registers if r.name == rname), None)
    return reg.offset if reg is not None else None


def analyze_consumer(files: List[str], comp_name: str,
                     config: FlowConfig, reporter: ErrorReporter
                     ) -> Optional[RegUsage]:
    """Parse *files* and return the RegUsage for component *comp_name* (or None)."""
    parser = Parser(config, reporter)
    if not parser.parse(files):
        return None
    classes = {c.name: c for c in collect_user_classes(parser.get_root())}
    comp = classes.get(comp_name)
    if comp is None:
        reporter.error(f"consumer component {comp_name!r} not found")
        return None
    rm = RegMapper(reporter)
    by_name = classes
    regmaps = {c.name: rm.build(c, by_name)
               for c in classes.values() if rm.is_reg_block_class(c)}
    return _Analyzer(rm, regmaps, reporter).analyze(comp)


class _Analyzer:
    def __init__(self, rm: RegMapper, regmaps: Dict[str, RegBlock],
                 reporter: ErrorReporter):
        self.rm = rm
        self.regmaps = regmaps
        self.reporter = reporter

    def analyze(self, comp) -> RegUsage:
        usage = RegUsage()
        # the component's register-block handle -> its RegMap (the root for refs)
        root_block: Optional[RegBlock] = None
        for m in comp:
            if m.kind == ast.SymbolKind.ClassProperty:
                tname = getattr(m.type, "name", None)
                if tname in self.regmaps:
                    root_block = self.regmaps[tname]
        if root_block is None:
            return usage          # consumer holds no register block

        for sub_name in ("new", "build"):
            sub = next((m for m in comp
                        if m.kind == ast.SymbolKind.Subroutine
                        and getattr(m, "name", None) == sub_name
                        and getattr(m, "body", None) is not None), None)
            if sub is not None:
                for s in self.rm._stmts(sub.body):
                    self._scan(s, root_block, usage, env={})
        # stable order for deterministic emission
        for k in usage.change_sets:
            usage.change_sets[k].sort()
        usage.observers.sort()
        usage.providers.sort()
        return usage

    def _scan(self, s, root_block, usage, env):
        if s.kind == ast.StatementKind.ForLoop:
            var, vals = self.rm._loop_range(s, env)
            if var is None or vals is None:
                return
            for iv in vals:
                e2 = dict(env)
                e2[var] = iv
                for bs in self.rm._stmts(s.body):
                    self._scan(bs, root_block, usage, e2)
            return
        if s.kind != ast.StatementKind.ExpressionStatement:
            return
        e = s.expr
        if e.kind != ast.ExpressionKind.Call:
            return
        method = getattr(e, "subroutineName", None)
        if method == "add":
            # <set>.add(<reg-ref>)  -- thisClass is the watch-set variable
            set_name = self._name_of(getattr(e, "thisClass", None))
            if set_name is None or not e.arguments:
                return
            off = self._chain_offset(e.arguments[0], root_block, env)
            if off is not None:
                usage.change_sets.setdefault(set_name, []).append(off)
        elif method in ("set_rd", "add_wr"):
            # <reg-ref>.set_rd(...) / .add_wr(...)
            off = self._chain_offset(getattr(e, "thisClass", None), root_block, env)
            if off is not None:
                (usage.providers if method == "set_rd"
                 else usage.observers).append(off)

    @staticmethod
    def _name_of(e) -> Optional[str]:
        if e is None:
            return None
        sym = getattr(e, "symbol", None)
        return getattr(sym, "name", None) if sym is not None else None

    def _chain_offset(self, e, root_block: RegBlock, env) -> Optional[int]:
        return resolve_chain_offset(e, root_block, self.rm, env)
