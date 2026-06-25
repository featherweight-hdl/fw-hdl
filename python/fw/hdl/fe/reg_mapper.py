"""Recognize fw-hdl register-block classes and elaborate them into a ``RegBlock``.

This is the M5 step of the register-model plan: walk a class that extends
``fw_reg_block`` and recover, from its declarations and constructor, the flat
register/field description (``fw.hdl.regmap``). It handles the straight-line
construction pattern (member ``fw_reg #(T) r;`` + ``r = new(...)`` + ``add(r)`` /
``add(r, OFFSET)`` / ``add_block(sub, OFFSET)``) and constant-folds offsets, reset
values, and the sw/hw/rclr masks — including masks supplied by a single-``return``
struct-literal helper function (the DMA CSR pattern).

Constructs it cannot constant-fold are *recorded* (``Register.unresolved`` / a
reporter note), never silently dropped.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pyslang import ast

from ..config import FlowConfig
from ..errors import ErrorReporter
from ..regmap import RegBlock, Register, RegField
from .astdump import collect_user_classes
from .expr_mapper import const_to_int, parse_int_token
from .parser import Parser

# fw_reg constructor formal order: new(name, reset, sw_wmask, hw_wmask, rclr_mask)
_ARG_RESET, _ARG_SW, _ARG_HW, _ARG_RCLR = 1, 2, 3, 4


def build_reg_blocks(files: List[str],
                     config: FlowConfig,
                     reporter: ErrorReporter) -> Dict[str, RegBlock]:
    """Parse *files* (with the fw-hdl library) and elaborate every register-block
    class into a ``RegBlock``. Returns {class_name: RegBlock} (empty on parse error)."""
    parser = Parser(config, reporter)
    if not parser.parse(files):
        return {}
    classes = list(collect_user_classes(parser.get_root()))
    by_name = {c.name: c for c in classes}
    mapper = RegMapper(reporter)
    return {c.name: mapper.build(c, by_name)
            for c in classes if mapper.is_reg_block_class(c)}


class RegMapper:
    def __init__(self, reporter: ErrorReporter):
        self.reporter = reporter

    # -- class discovery -------------------------------------------------
    @staticmethod
    def _derives_from(cls_sym, base_name: str) -> bool:
        bc = getattr(cls_sym, "baseClass", None)
        while bc is not None:
            if getattr(bc, "name", None) == base_name:
                return True
            bc = getattr(bc, "baseClass", None)
        return False

    def is_reg_block_class(self, cls_sym) -> bool:
        return (cls_sym.kind == ast.SymbolKind.ClassType
                and self._derives_from(cls_sym, "fw_reg_block"))

    # -- public entry ----------------------------------------------------
    def build(self, cls_sym, by_name: Optional[Dict[str, object]] = None) -> RegBlock:
        """Elaborate *cls_sym* (a fw_reg_block subclass) into a RegBlock."""
        by_name = by_name if by_name is not None else {}
        blk = RegBlock(name=cls_sym.name)

        # 1. catalog the register / sub-block properties of this class
        reg_props: Dict[str, Tuple[object, int]] = {}   # name -> (T_type, W)
        sub_props: Dict[str, object] = {}               # name -> element class sym
        for m in cls_sym:
            if m.kind != ast.SymbolKind.ClassProperty:
                continue
            info = self._reg_prop(m)
            if info is not None:
                reg_props[m.name] = info
                continue
            sub = self._subblock_prop(m)
            if sub is not None:
                sub_props[m.name] = sub

        # 2. read the constructor: register ctor args + add()/add_block() order
        ctor = self._find_new(cls_sym)
        ctor_args: Dict[str, object] = {}               # regname -> constructorCall
        add_order: List[Tuple[str, Optional[int]]] = []  # (regname, offset|None)
        addblk_order: List[Tuple[str, Optional[int]]] = []
        if ctor is not None:
            for s in self._stmts(ctor.body):
                self._scan_ctor_stmt(s, reg_props, ctor_args, add_order, addblk_order,
                                     env={})

        # 3. realize registers in add() order, assigning offsets
        cursor = 0
        stride = 4
        for (rname, off) in add_order:
            T_type, W = reg_props[rname]
            stride = W // 8
            o = off if (off is not None and off >= 0) else cursor
            reg = self._make_register(rname, o, W, T_type, ctor_args.get(rname))
            blk.registers.append(reg)
            cursor = o + stride
            blk.size = max(blk.size, o + stride)

        # 4. nested sub-blocks
        for (sname, off) in addblk_order:
            sub_cls = sub_props.get(sname)
            if sub_cls is None:
                self.reporter.error(f"add_block of unknown sub-block {sname!r}")
                continue
            sub_blk = self.build(sub_cls, by_name)
            o = off if (off is not None and off >= 0) else cursor
            blk.subblocks.append((o, sub_blk))
            cursor = o + sub_blk.size
            blk.size = max(blk.size, o + sub_blk.size)

        return blk

    # -- property recognition --------------------------------------------
    def _reg_prop(self, m) -> Optional[Tuple[object, int]]:
        """If *m* is an ``fw_reg #(T, W)`` property, return (T_type, W)."""
        t = m.type
        if getattr(t, "name", None) != "fw_reg":
            return None
        T_type, W = None, 32
        for sub in t:
            if sub.kind == ast.SymbolKind.TypeParameter and sub.name == "T":
                tt = getattr(sub, "targetType", None)
                T_type = getattr(tt, "type", None) if tt is not None else None
            elif sub.kind == ast.SymbolKind.Parameter and sub.name == "W":
                w = parse_int_token(str(getattr(sub, "value", "32")))
                if w is not None:
                    W = w
        return (T_type, W)

    def _subblock_prop(self, m):
        """If *m* is a (possibly arrayed) fw_reg_block-derived property, return its
        element class symbol."""
        t = m.type
        # unpacked array of class -> element type
        elem = getattr(t, "arrayElementType", None) or t
        if getattr(elem, "kind", None) == ast.SymbolKind.ClassType \
                and self._derives_from(elem, "fw_reg_block"):
            return elem
        return None

    # -- constructor scanning --------------------------------------------
    def _scan_ctor_stmt(self, s, reg_props, ctor_args, add_order, addblk_order, env):
        # affine for-loop over a channel array: unroll with the loop var bound.
        if s.kind == ast.StatementKind.ForLoop:
            var, vals = self._loop_range(s, env)
            if var is None or vals is None:
                self.reporter.warning(
                    "unrecognized for-loop in register-block constructor; "
                    "array members skipped")
                return
            for iv in vals:
                e2 = dict(env)
                e2[var] = iv
                for bs in self._stmts(s.body):
                    self._scan_ctor_stmt(bs, reg_props, ctor_args,
                                         add_order, addblk_order, e2)
            return
        if s.kind != ast.StatementKind.ExpressionStatement:
            return
        e = s.expr
        if e.kind == ast.ExpressionKind.Assignment:
            lname = getattr(getattr(e.left, "symbol", None), "name", None)
            if lname in reg_props and e.right.kind == ast.ExpressionKind.NewClass:
                cc = getattr(e.right, "constructorCall", None)
                if cc is not None:
                    ctor_args[lname] = cc
        elif e.kind == ast.ExpressionKind.Call:
            name = getattr(e, "subroutineName", None)
            if name in ("add", "add_block"):
                args = list(e.arguments)
                target = self._ref_name(args[0]) if args else None
                off = self._eval_int(args[1], env) if len(args) > 1 else None
                if target is None:
                    return
                if name == "add":
                    add_order.append((target, off))
                else:
                    addblk_order.append((target, off))

    @staticmethod
    def _ref_name(e) -> Optional[str]:
        """Resolve the register/sub-block name from an add() argument, unwrapping
        a Conversion and an element-select (``ch[i]`` -> ``ch``)."""
        if e.kind == ast.ExpressionKind.Conversion:
            return RegMapper._ref_name(e.operand)
        if e.kind == ast.ExpressionKind.ElementSelect:
            return RegMapper._ref_name(e.value)
        sym = getattr(e, "symbol", None)
        return getattr(sym, "name", None) if sym is not None else None

    # -- register realization --------------------------------------------
    def _make_register(self, name, offset, W, T_type, cc) -> Register:
        fields_layout = self._struct_fields(T_type, W)
        reg = Register(name=name, offset=offset, width=W)

        unresolved: List[str] = []
        reset = self._mask_arg(cc, _ARG_RESET, fields_layout, W, name, "reset", unresolved) or 0
        swm = self._mask_arg(cc, _ARG_SW, fields_layout, W, name, "sw_wmask", unresolved)
        hwm = self._mask_arg(cc, _ARG_HW, fields_layout, W, name, "hw_wmask", unresolved)
        rcm = self._mask_arg(cc, _ARG_RCLR, fields_layout, W, name, "rclr_mask", unresolved)
        # defaults if absent / unresolved: sw all-writable, hw none, rclr none
        sw_wmask = swm if swm is not None else (1 << W) - 1
        hw_wmask = hwm if hwm is not None else 0
        rclr_mask = rcm if rcm is not None else 0

        reg.reset, reg.sw_wmask, reg.hw_wmask, reg.rclr_mask = \
            reset, sw_wmask, hw_wmask, rclr_mask
        reg.unresolved = tuple(unresolved)

        for (fname, lsb, width) in fields_layout:
            fmask = ((1 << width) - 1) << lsb
            reg.fields.append(RegField(
                name=fname, lsb=lsb, width=width,
                sw_write=bool(sw_wmask & fmask),
                hw_write=bool(hw_wmask & fmask),
                rclr=bool(rclr_mask & fmask),
                reset=(reset >> lsb) & ((1 << width) - 1)))
        return reg

    def _struct_fields(self, T_type, W) -> List[Tuple[str, int, int]]:
        """Return [(field_name, lsb, width)] for T. A non-struct (integral) T is a
        single anonymous ``value`` field spanning the whole word."""
        if T_type is None:
            return [("value", 0, W)]
        ct = getattr(T_type, "canonicalType", None) or T_type
        if not getattr(ct, "isStruct", False):
            return [("value", 0, W)]
        out: List[Tuple[str, int, int]] = []
        for f in ct:
            if f.kind != ast.SymbolKind.Field:
                continue
            width = int(getattr(f.type, "bitWidth", 1))
            out.append((f.name, int(f.bitOffset), width))
        return out

    # -- value / mask evaluation -----------------------------------------
    def _mask_arg(self, cc, idx, fields_layout, W, regname, what, unresolved) -> Optional[int]:
        if cc is None:
            return None
        args = list(getattr(cc, "arguments", []) or [])
        if idx >= len(args):
            return None
        e = args[idx]
        v = self._eval_value(e, fields_layout, W)
        if v is None:
            unresolved.append(what)
            self.reporter.warning(f"register {regname!r}: could not constant-fold {what}")
            return None
        return v & ((1 << W) - 1)

    def _eval_value(self, e, fields_layout, W) -> Optional[int]:
        """Evaluate a constructor argument to a W-bit integer value."""
        if e.kind == ast.ExpressionKind.Conversion:
            return self._eval_value(e.operand, fields_layout, W)
        if e.kind == ast.ExpressionKind.Call:
            return self._eval_mask_fn(e, fields_layout, W)
        if e.kind == ast.ExpressionKind.StructuredAssignmentPattern:
            return self._eval_struct_pattern(e, fields_layout, W)
        return self._eval_int(e, {})

    def _eval_mask_fn(self, call_e, fields_layout, W) -> Optional[int]:
        """A mask supplied by a static helper: evaluate its single ``return``
        struct-literal (the DMA csr_*_wmask() pattern)."""
        sub = getattr(call_e, "subroutine", None)
        body = getattr(sub, "body", None) if sub is not None else None
        if body is None:
            return None
        ret = None
        for s in self._stmts(body):
            if s.kind == ast.StatementKind.Return:
                ret = s
                break
        if ret is None:
            return None
        re = getattr(ret, "expr", None)
        if re is None:
            return None
        if re.kind == ast.ExpressionKind.StructuredAssignmentPattern:
            return self._eval_struct_pattern(re, fields_layout, W)
        return self._eval_int(re, {})

    def _eval_struct_pattern(self, pat, fields_layout, W) -> Optional[int]:
        """Evaluate a packed-struct '{...} pattern to a W-bit value. ``.elements``
        align 1:1 with the struct fields in declaration order (default already
        expanded)."""
        elems = list(getattr(pat, "elements", []) or [])
        if len(elems) != len(fields_layout):
            return None
        value = 0
        for (fname, lsb, width), el in zip(fields_layout, elems):
            v = self._eval_int(el, {})
            if v is None:
                return None
            value |= (v & ((1 << width) - 1)) << lsb
        return value

    def _eval_int(self, e, env: Dict[str, int]) -> Optional[int]:
        """Constant-fold an integer expression (with an env for loop variables)."""
        k = e.kind
        if k == ast.ExpressionKind.Conversion:
            return self._eval_int(e.operand, env)
        if k == ast.ExpressionKind.UnbasedUnsizedIntegerLiteral:
            return parse_int_token(str(getattr(e, "value", "")))
        if k == ast.ExpressionKind.IntegerLiteral:
            v = const_to_int(getattr(e, "constant", None))
            return v if v is not None else parse_int_token(str(getattr(e, "value", "")))
        if k == ast.ExpressionKind.NamedValue:
            sym = getattr(e, "symbol", None)
            nm = getattr(sym, "name", None)
            if nm in env:
                return env[nm]
            v = const_to_int(getattr(e, "constant", None))
            if v is not None:
                return v
            # a localparam / parameter symbol carries its folded value
            val = getattr(sym, "value", None)
            return parse_int_token(str(val)) if val is not None else None
        if k == ast.ExpressionKind.UnaryOp:
            v = self._eval_int(e.operand, env)
            if v is None:
                return None
            if e.op == ast.UnaryOperator.Minus:
                return -v
            if e.op == ast.UnaryOperator.Plus:
                return v
            return None
        if k == ast.ExpressionKind.BinaryOp:
            l = self._eval_int(e.left, env)
            r = self._eval_int(e.right, env)
            if l is None or r is None:
                return None
            op = e.op
            if op == ast.BinaryOperator.Add:
                return l + r
            if op == ast.BinaryOperator.Subtract:
                return l - r
            if op == ast.BinaryOperator.Multiply:
                return l * r
            return None
        return const_to_int(getattr(e, "constant", None))

    # -- misc ------------------------------------------------------------
    @staticmethod
    def _find_new(cls_sym):
        for m in cls_sym:
            if (m.kind == ast.SymbolKind.Subroutine
                    and getattr(m, "name", None) == "new"
                    and getattr(m, "body", None) is not None):
                return m
        return None

    def _stmts(self, body) -> List[object]:
        """Flatten a body into a statement list, descending List and Block (a
        ``for`` introduces a Block holding the loop-var decl + the ForLoop)."""
        if body is None:
            return []
        if body.kind == ast.StatementKind.List:
            out = []
            for s in body.list:
                if s.kind in (ast.StatementKind.List, ast.StatementKind.Block):
                    out.extend(self._stmts(s))
                else:
                    out.append(s)
            return out
        if body.kind == ast.StatementKind.Block:
            return self._stmts(body.body)
        return [body]

    def _loop_range(self, fl, env) -> Tuple[Optional[str], Optional[List[int]]]:
        """Recognize ``for (i = 0; i < N; i++)`` and return (var, [0..N-1]).

        Assumes the canonical zero-based unit-stride form (the DMA channel-array
        pattern); anything else returns (None, None) and is logged by the caller.
        """
        se = getattr(fl, "stopExpr", None)
        if se is None or se.kind != ast.ExpressionKind.BinaryOp:
            return (None, None)
        var = getattr(getattr(se.left, "symbol", None), "name", None)
        n = self._eval_int(se.right, env)
        if var is None or n is None:
            return (None, None)
        if se.op == ast.BinaryOperator.LessThan:
            return (var, list(range(0, n)))
        if se.op == ast.BinaryOperator.LessThanEqual:
            return (var, list(range(0, n + 1)))
        return (None, None)
