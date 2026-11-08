"""Component structure: the children, channels and connections of a structural
component, as zuspec IR.

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
``get_ex`` / ``get_nb_ex`` (the last for a polling ``fw_get_nb_if`` port; a
channel has exactly one consumer end).

``build()`` and ``connect()`` are elaborated, not read: they run in
the path-D interpreter (:mod:`.elab.hier`), so loops, ``if`` on parameters,
arrays of children, ports and channels (``x[i]``, RTL name ``x_i``) and
``fw_component_param`` objects all work. What is checked is meaning, at the SV
line that broke it: child-to-child binds, ends left unconnected or connected
twice, an instance name that differs from its field, and a component with both
children and ``run()``.

Each distinct child (its class specialization plus its parameter-object
values) is one generated block. A plain class or a typedef keeps its name; a
bare specialization or a parameter object is named ``<class>__<hash8>``
(:meth:`.elab.hier.Node.spelling`), with the SV class kept as a readable alias.
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
    #: The elaborated instance (.elab.hier.Node): its parameter object, binds, children.
    node: object = None
    #: A structural child's own structure (None for a leaf).
    structure: Optional["Structure"] = None

    @property
    def param_values(self) -> Dict[str, object]:
        """``m_params.<field>`` values, folded into constants by the static mapper."""
        return dict(self.node.param_obj) if self.node is not None else {}

    @property
    def alias(self) -> str:
        """The SV class this block was generated from (readable, not unique)."""
        return str(self.cls)


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
        from .elab.hier import HierError, elaborate_tree
        from .elab.interp import ElabError
        self.fields, self.port_dirs = {}, {}
        self.cls_name, self.cls_spelling = cls.name, spelling or cls.name
        from .static_mapper import find_behavior
        try:
            kind, run = find_behavior(cls)
        except ValueError as e:
            kind, run = "step", e.args[0]
        if run is not None:
            what = "a run() task" if kind == "run" else "a step()"
            raise self.fail(f"class {cls.name!r} has children and {what}; a component is "
                            f"either structural (build/connect) or a process (run, step), "
                            f"not both", run)
        try:
            node = elaborate_tree(cls.compilation, cls, self.cls_spelling)
        except HierError as e:
            raise self.fail(str(e), e.node) from None
        except ElabError as e:
            raise self.fail(f"elaborating {cls.name}: {e}", cls) from None
        return self.from_node(node, self.cls_spelling)

    def from_node(self, node, spelling: str) -> Structure:
        """The structure of one elaborated structural instance; a structural
        child gets its own (``Child.structure``)."""
        saved = (self.fields, self.port_dirs, self.cls_name, self.cls_spelling)
        self.fields, self.port_dirs = {}, {}
        self.cls_name, self.cls_spelling = node.cls.name, spelling
        try:
            return self._from_node(node)
        finally:
            self.fields, self.port_dirs, self.cls_name, self.cls_spelling = saved

    def _from_node(self, node) -> Structure:
        cls = node.cls
        fields: List[ir.Field] = []
        children: Dict[str, Child] = {}
        for name, p in node.ports.items():
            ctype = None if p.index is None else p.prop.type.canonicalType.arrayElementType
            f = self.port_field(p.prop, name=name, ctype=ctype)
            self.fields[name] = len(fields)
            fields.append(f)
        for name, ch in node.channels.items():
            et = self.dtype(ch.elem_type, ch.prop, f"payload of channel {name!r}", decl=True)
            self.fields[name] = len(fields)
            fields.append(ir.Field(name=name, datatype=ir.DataTypeChannel(element_type=et,
                                                                          depth=ch.depth),
                                   loc=self.loc(ch.prop),
                                   pragmas={"fw_role": "channel", "sv_type": str(ch.elem_type),
                                            "fw_kind": ch.kind}))
        for name, c in node.children.items():
            sp = c.spelling()
            children[name] = Child(name, c.cls, sp, self._child_ports(c.cls, sp, c), c.prop, c,
                                   self.from_node(c, sp) if c.structural else None)
            self.fields[name] = len(fields)
            fields.append(ir.Field(name=name, datatype=ir.DataTypeRef(ref_name=sp),
                                   loc=self.loc(c.prop),
                                   pragmas={"fw_role": "child", "sv_class": sp,
                                            "alias": str(c.cls)}))
        comp = ir.DataTypeComponent(name=self.cls_spelling, super=None, fields=fields,
                                    loc=self.loc(node.prop or cls))
        comp.bind_map = [ir.Bind(lhs=self._ref(child, port), rhs=self._ref(pname, end))
                         for (child, port), (pname, end) in node.binds]
        return Structure(comp, children)

    def _ref(self, name: str, attr: Optional[str]) -> ir.Expr:
        base = ir.ExprRefField(base=ir.TypeExprRefSelf(), index=self.fields[name])
        return base if attr is None else ir.ExprAttribute(value=base, attr=attr)

    def _child_ports(self, ct, spelling: str, node=None) -> Dict[str, ir.Field]:
        """The child's port fields, by RTL name. From the elaborated *node*
        when there is one, so an array of ports gives one field per element
        (``in[2]`` -> ``in_2``)."""
        saved = (self.cls_name, self.cls_spelling, self.port_dirs)
        self.cls_name, self.cls_spelling, self.port_dirs = ct.name, spelling, {}
        try:
            ports = {}
            if node is not None:
                for name, p in node.ports.items():
                    ctype = None if p.index is None else \
                        p.prop.type.canonicalType.arrayElementType
                    ports[name] = self.port_field(p.prop, name=name, ctype=ctype)
                return ports
            c = ct
            while c is not None and c.kind == ast.SymbolKind.ClassType \
                    and _generic_name(c) not in ("fw_component", "fw_component_param"):
                for m in c:
                    if m.kind == ast.SymbolKind.ClassProperty and m.name not in ports:
                        f = self.port_field(m)
                        if f is not None:
                            ports[m.name] = f
                b = c.baseClass
                c = b.canonicalType if b is not None else None
            return ports
        finally:
            self.cls_name, self.cls_spelling, self.port_dirs = saved
