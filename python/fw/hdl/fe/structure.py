"""Component structure: the children, channels and connections of a structural
component, as zuspec IR (``xls-phase2.md`` ST-2).

A *structural* component has no ``run()``. It only builds and connects:

    class chain_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;       // its own ports: the boundary
        rle_enc8_t                 rle;              // child components
        fw_channel #(pkt_t, 0)     c0;               // channels between them
        function void build();
            in = new("in", this);  rle = new("rle", this);  c0 = new("c0", this);
        endfunction
        function void connect();
            rle.in.connect(in);                      // child port -> own port
            rle.out.connect(c0.put_ex);              // child port -> channel export
        endfunction
    endclass

maps to a ``DataTypeComponent`` whose fields are

* the component's own ports (``FieldKind.Port``, as the static mapper maps them);
* one field per child, typed ``DataTypeRef(<spelling>)``;
* one field per channel, typed ``DataTypeChannel(element_type, depth)``;

and whose ``bind_map`` holds one ``Bind(lhs=<child port>, rhs=<provider>)`` per
``connect()`` call. The provider is an own port or a channel's ``put_ex`` /
``get_ex``.

``build()`` and ``connect()`` must be straight-line: one ``x = new("x", this)``
per field, and one ``<child>.<port>.connect(<provider>)`` per child port. Anything
else is rejected at its SV line; the structure is read, not elaborated.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional, Tuple

import zuspec.ir.core as ir
from pyslang import ast

from .static_mapper import StaticMapper


@dc.dataclass
class Child:
    """A child component: what the partition step maps next."""
    name: str
    cls: object                 # pyslang ClassType (the specialization)
    spelling: str               # how SV names it: a class name or a typedef
    ports: Dict[str, ir.Field]  # its fw_port fields, as the static mapper maps them
    decl: object = None         # the property declaring it (for diagnostics)


@dc.dataclass
class Structure:
    component: ir.DataTypeComponent
    children: Dict[str, Child]


def _generic_name(ct) -> Optional[str]:
    g = getattr(ct, "genericClass", None)
    return g.name if g is not None else getattr(ct, "name", None)


def _is_component(ct) -> bool:
    while ct is not None and ct.kind == ast.SymbolKind.ClassType:
        if _generic_name(ct) == "fw_component":
            return True
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return False


def _strip(e):
    while e.kind == ast.ExpressionKind.Conversion:
        e = e.operand
    return e


class StructureMapper(StaticMapper):
    """Maps a structural component class (no ``run()``)."""

    def map_structure(self, cls, spelling: Optional[str] = None) -> Structure:
        self.fields, self.port_dirs = {}, {}
        self.cls_name, self.cls_spelling = cls.name, spelling or cls.name
        fields: List[ir.Field] = []
        children: Dict[str, Child] = {}
        build = connect = None
        for m in cls:
            if m.kind == ast.SymbolKind.ClassProperty:
                f = self._structural_field(m, children)
                self.fields[m.name] = len(fields)
                fields.append(f)
            elif m.kind == ast.SymbolKind.Subroutine and m.body is not None:
                if m.name == "run":
                    raise self.fail(
                        f"class {cls.name!r} has children and a run() task; a component is "
                        f"either structural (build/connect) or a process (run), not both", m)
                if m.name == "build":
                    build = m
                elif m.name == "connect":
                    connect = m
        comp = ir.DataTypeComponent(name=self.cls_spelling, super=None, fields=fields,
                                    loc=self.loc(cls))
        self._check_build(cls, build, fields)
        comp.bind_map = self._binds(cls, connect, fields, children)
        return Structure(comp, children)

    # ------------------------------------------------------------------
    def _structural_field(self, m, children: Dict[str, Child]) -> ir.Field:
        f = self.port_field(m)
        if f is not None:
            return f
        t = m.type
        ct = t.canonicalType
        if ct.kind != ast.SymbolKind.ClassType or not _is_component(ct):
            raise self.fail(f"property {m.name!r}: a structural component holds only ports, "
                            f"child components and channels", m)
        if _generic_name(ct) == "fw_channel":
            return self._channel_field(m, ct)
        if ct.genericClass is not None and not t.isAlias:
            raise self.fail(f"child {m.name!r}: a specialization of a parameterized class "
                            f"needs a typedef, which names its generated block",
                            m, suggestion=f"typedef {t} <name>_t; and declare {m.name} as <name>_t")
        spelling = t.name
        children[m.name] = Child(m.name, ct, spelling, self._child_ports(ct, spelling), m)
        return ir.Field(name=m.name, datatype=ir.DataTypeRef(ref_name=spelling),
                        loc=self.loc(m), pragmas={"fw_role": "child", "sv_class": spelling})

    def _channel_field(self, m, ct) -> ir.Field:
        elem = depth = None
        for x in ct:
            if x.kind == ast.SymbolKind.TypeParameter and x.name == "T":
                elem = x.targetType.type
            elif x.kind == ast.SymbolKind.Parameter and x.name == "DEPTH":
                depth = self.svint_value(x.value.value)
        if elem is None or depth is None or depth < 0:
            raise self.fail(f"channel {m.name!r}: cannot read its type and DEPTH", m)
        et = self.dtype(elem, m, f"payload of channel {m.name!r}", decl=True)
        return ir.Field(name=m.name, datatype=ir.DataTypeChannel(element_type=et, depth=depth),
                        loc=self.loc(m), pragmas={"fw_role": "channel", "sv_type": str(elem)})

    def _child_ports(self, ct, spelling: str) -> Dict[str, ir.Field]:
        saved = (self.cls_name, self.cls_spelling, self.port_dirs)
        self.cls_name, self.cls_spelling, self.port_dirs = ct.name, spelling, {}
        try:
            ports = {}
            for m in ct:
                if m.kind == ast.SymbolKind.ClassProperty:
                    f = self.port_field(m)
                    if f is not None:
                        ports[m.name] = f
            return ports
        finally:
            self.cls_name, self.cls_spelling, self.port_dirs = saved

    # ------------------------------------------------------------------
    def _stmts(self, sub) -> list:
        b = sub.body
        return list(b.list) if b.kind == ast.StatementKind.List else [b]

    @staticmethod
    def _is_super_call(e, name: str) -> bool:
        return e.kind == ast.ExpressionKind.Call and e.subroutineName == name \
            and e.thisClass is None

    def _check_build(self, cls, build, fields: List[ir.Field]) -> None:
        built: Dict[str, object] = {}
        for s in (self._stmts(build) if build is not None else []):
            e = s.expr if s.kind == ast.StatementKind.ExpressionStatement else None
            if e is not None and self._is_super_call(e, "build"):
                continue
            ok = e is not None and e.kind == ast.ExpressionKind.Assignment \
                and e.left.kind == ast.ExpressionKind.NamedValue \
                and e.left.symbol.name in self.fields \
                and e.right.kind == ast.ExpressionKind.NewClass
            if not ok:
                raise self.fail("build() of a structural component may only construct its "
                                "fields: `x = new(\"x\", this);`", s)
            name = e.left.symbol.name
            if name in built:
                raise self.fail(f"{name!r} is constructed twice", s)
            args = e.right.constructorCall.arguments if e.right.constructorCall else []
            inst = _strip(args[0]) if args else None
            if inst is None or inst.kind != ast.ExpressionKind.StringLiteral \
                    or inst.value != name:
                raise self.fail(f"{name!r} must be constructed as new(\"{name}\", this): the "
                                f"name becomes the RTL instance name", s)
            built[name] = s
        missing = [f.name for f in fields if f.name not in built]
        if missing:
            raise self.fail(f"build() of {cls.name!r} does not construct {missing}",
                            build or cls)

    def _endpoint(self, e, node) -> Tuple[ir.Expr, str]:
        """An IR expression for a connect() operand, and a readable name."""
        e = _strip(e)
        if e.kind == ast.ExpressionKind.NamedValue and e.symbol.name in self.fields:
            n = e.symbol.name
            return ir.ExprRefField(base=ir.TypeExprRefSelf(), index=self.fields[n]), n
        if e.kind == ast.ExpressionKind.MemberAccess:
            v = _strip(e.value)
            if v.kind == ast.ExpressionKind.NamedValue and v.symbol.name in self.fields:
                n = v.symbol.name
                return (ir.ExprAttribute(
                    value=ir.ExprRefField(base=ir.TypeExprRefSelf(), index=self.fields[n]),
                    attr=e.member.name), f"{n}.{e.member.name}")
        raise self.fail("connect() operands must be `child.port`, `channel.put_ex` / "
                        "`channel.get_ex`, or one of this component's ports", node)

    def _binds(self, cls, connect, fields: List[ir.Field],
               children: Dict[str, Child]) -> List[ir.Bind]:
        kind = {f.name: f.pragmas.get("fw_role", "port") for f in fields}
        binds: List[ir.Bind] = []
        used: Dict[str, object] = {}

        def use(name: str, node):
            if name in used:
                raise self.fail(f"{name} is connected twice; a channel end and a port "
                                f"each connect exactly once", node)
            used[name] = node

        for s in (self._stmts(connect) if connect is not None else []):
            e = s.expr if s.kind == ast.StatementKind.ExpressionStatement else None
            if e is not None and self._is_super_call(e, "connect"):
                continue
            if e is None or e.kind != ast.ExpressionKind.Call or e.subroutineName != "connect" \
                    or e.thisClass is None or len(e.arguments) != 1:
                raise self.fail("connect() of a structural component may only contain "
                                "`<child>.<port>.connect(<provider>);`", s)
            lhs, lname = self._endpoint(e.thisClass, s)
            rhs, rname = self._endpoint(e.arguments[0], s)
            owner = lname.split(".")[0]
            if kind.get(owner) != "child" or "." not in lname:
                raise self.fail(f"{lname}: only a child's port is connected (it is the "
                                f"consumer; the provider is the argument)", s)
            if lname.split(".")[1] not in children[owner].ports:
                raise self.fail(f"{lname} is not a port of {children[owner].spelling}", s)
            pown = rname.split(".")[0]
            if kind.get(pown) == "channel":
                if rname.split(".")[-1] not in ("put_ex", "get_ex"):
                    raise self.fail(f"{rname}: a channel's ends are put_ex and get_ex", s)
            elif kind.get(pown) != "port" or "." in rname:
                raise self.fail(f"{rname}: the provider must be a channel end or one of "
                                f"{cls.name}'s own ports (child-to-child needs a channel)", s)
            use(lname, s)
            use(rname, s)
            binds.append(ir.Bind(lhs=lhs, rhs=rhs))

        node = connect or cls
        for c in children.values():
            for p in c.ports:
                if f"{c.name}.{p}" not in used:
                    raise self.fail(f"port {c.name}.{p} is not connected", node)
        for f in fields:
            role = kind[f.name]
            if role == "port" and f.name not in used:
                raise self.fail(f"port {f.name} is not connected to a child", node)
            if role == "channel":
                for end in ("put_ex", "get_ex"):
                    if f"{f.name}.{end}" not in used:
                        raise self.fail(f"channel end {f.name}.{end} is not connected", node)
        return binds
