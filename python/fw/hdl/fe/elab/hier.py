"""Hierarchy-preserving elaboration of a structural component.

Runs the top class's real ``build()`` and ``connect()`` through the path-D
interpreter (:mod:`.interp`), so loops, conditions on parameters, arrays of
children and ``fw_component_param`` objects all work, and then reads the
object graph back as a tree:

    node = elaborate_tree(compilation, top_cls, source_manager)
    node.children["a"].cls          # the child's class (a specialization)
    node.binds                      # [((child, port), (provider, end)), ...]

No thread runs: only construction, ``do_build`` and ``do_connect``. Each node
records its class, its class parameters, the fields of its parameter object
(``m_params``), its own ports, its channels and children, and how its
children's ports are bound. The rules about meaning are checked here, at the
SV line that broke them: a child port bound to another child's port, an end
left unconnected or connected twice, an instance name that differs from the
field holding it, and a component with both children and ``run()``.
"""
from __future__ import annotations

import dataclasses as dc
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from pyslang import ast

from .interp import ElabError, Frame, Interpreter, Val
from .values import Iface, Obj, const_to_py

SK = ast.SymbolKind


class HierError(ElabError):
    """A structural rule is broken. ``node`` is the SV syntax to point at."""

    def __init__(self, msg: str, node=None):
        super().__init__(msg)
        self.node = node


def _generic(ct) -> Optional[str]:
    g = getattr(ct, "genericClass", None)
    return g.name if g is not None else getattr(ct, "name", None)


def _derives(ct, name: str) -> bool:
    while ct is not None and ct.kind == SK.ClassType:
        if _generic(ct) == name:
            return True
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return False


def _prop(ct, name: str):
    while ct is not None and ct.kind == SK.ClassType:
        m = ct.find(name)
        if m is not None and m.kind == SK.ClassProperty:
            return m
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    raise ElabError(f"{ct} has no property {name}")


def _sub(ct, name: str):
    while ct is not None and ct.kind == SK.ClassType:
        m = ct.find(name)
        if m is not None and m.kind == SK.Subroutine:
            return m
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return None


def _own_step(ct):
    """The user class's own step(), when it is an fw_steppable."""
    from ..static_mapper import _implements
    return _own_sub(ct, "step") if _implements(ct, "fw_steppable") else None


def _own_sub(ct, name: str):
    """*name* defined by the user class itself or a user base (not the library)."""
    while ct is not None and ct.kind == SK.ClassType:
        if _generic(ct) in ("fw_component", "fw_component_param"):
            return None
        m = ct.find(name)
        if m is not None and m.kind == SK.Subroutine and m.body is not None:
            return m
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return None


def _declared_sub(ct, name: str):
    """*name* declared in the user class or a user base, not inherited from
    the library (``find`` also sees fw_component's default)."""
    while ct is not None and ct.kind == SK.ClassType \
            and _generic(ct) not in ("fw_component", "fw_component_param"):
        for m in ct:
            if m.kind == SK.Subroutine and m.name == name:
                return m
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    return None


def _implements_extern(ct) -> bool:
    from ..static_mapper import _implements
    return _implements(ct, "fw_extern_impl")


def channel_kinds() -> Dict[str, str]:
    """The channel classes and the kind each one is (registry entries,
    ``fw.hdl.lib.registry``)."""
    from ...lib.registry import channel_kinds as _ck
    return _ck()


def _channel_class(ct) -> Optional[str]:
    return next((c for c in channel_kinds() if _derives(ct, c)), None)


def rtl_name(name: str) -> str:
    """An instance name as an RTL identifier: ``x[2]`` -> ``x_2``."""
    out = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


@dc.dataclass
class Port:
    name: str                   # RTL name
    obj: Obj
    cls: Any                    # fw_port specialization
    prop: Any                   # the class property holding it
    index: Optional[int] = None


@dc.dataclass
class Channel:
    name: str
    obj: Obj
    cls: Any                    # fw_channel specialization
    prop: Any
    index: Optional[int] = None

    @property
    def elem_type(self):
        for x in self.cls:
            if x.kind == SK.TypeParameter and x.name == "T":
                return x.targetType.type
        raise ElabError(f"channel {self.name}: no T")

    @property
    def kind(self) -> str:
        """``ready_valid`` (fw_channel), ``valid`` or ``level``."""
        return channel_kinds()[_channel_class(self.cls)]

    @property
    def depth(self) -> int:
        for x in self.cls:
            if x.kind == SK.Parameter and x.name == "DEPTH":
                return int(const_to_py(x.value))
        if self.kind == "level":
            return 0
        raise ElabError(f"channel {self.name}: no DEPTH")


@dc.dataclass
class Node:
    """One component instance of the elaborated tree."""
    path: str
    name: str                   # RTL instance name
    obj: Obj
    cls: Any                    # the runtime ClassType (a specialization)
    prop: Any = None            # the parent's property holding it (None for the top)
    index: Optional[int] = None
    decl_type: Any = None       # the property's declared type (a typedef, say)
    params: Dict[str, str] = dc.field(default_factory=dict)       # class parameters
    param_obj: Dict[str, Any] = dc.field(default_factory=dict)    # m_params fields
    ports: Dict[str, Port] = dc.field(default_factory=dict)       # own fw_port endpoints
    channels: Dict[str, Channel] = dc.field(default_factory=dict)
    children: Dict[str, "Node"] = dc.field(default_factory=dict)
    #: ((child, port field), (provider, end)); end is put_ex/get_ex/get_nb_ex
    #: for a channel and None for one of this node's own ports.
    binds: List[Tuple[Tuple[str, str], Tuple[str, Optional[str]]]] = dc.field(default_factory=list)
    has_run: bool = False
    #: A wrapper's extern_map() (:class:`fw.hdl.extern.ExternRecord`), or None.
    extern: Any = None
    #: What a leaf's facts() declared (:class:`fw.hdl.facts.BlockFact`), ports
    #: by RTL name.
    facts: List[Any] = dc.field(default_factory=list)

    @property
    def structural(self) -> bool:
        return bool(self.children)

    def key(self) -> str:
        """What makes two instances the same generated block: the class
        (a specialization carries its parameters) and the parameter object."""
        return f"{self.cls}|{sorted(self.param_obj.items())!r}"

    def spelling(self) -> str:
        """How the generated block is named. A plain class or a typedef keeps
        its SV name; a bare specialization, or a parameter object, adds a hash
        of what distinguishes it (``<class>__<hash8>``)."""
        t = self.decl_type
        base = t.name if t is not None and getattr(t, "isAlias", False) else None
        if base is None and getattr(self.cls, "genericClass", None) is None:
            base = self.cls.name
        if base is not None and not self.param_obj:
            return base
        h = hashlib.sha256(self.key().encode()).hexdigest()[:8]
        return f"{base or _generic(self.cls)}__{h}"


class _Recorder(Interpreter):
    """The interpreter, noting where each object was constructed and every
    port/export ``connect`` call, for diagnostics."""

    def __init__(self, compilation, top_inst=None):
        super().__init__(compilation, top_inst)
        self.created: Dict[int, Any] = {}       # oid -> the `new` call expression
        self.connects: List[Tuple[Obj, Any, Any]] = []   # (endpoint, provider, call)
        #: fw_extern_map / fw_facts oid -> [(method, call site)], in call order.
        self.map_calls: Dict[int, List[Tuple[str, Any]]] = {}

    def construct(self, cls, call_expr, caller: Frame):
        o = super().construct(cls, call_expr, caller)
        site = caller.pos[-1] if caller is not None and caller.pos else call_expr
        self.created[o.oid] = site
        return o

    def call_sub(self, sub, this, iface, args, caller, call_expr):
        # An unbound port is the boundary (the top's own ports): its provider
        # comes from the shell, so resolving it gives null, not $fatal.
        if sub.name == "get_if" and isinstance(this, Obj) and _derives(this.cls, "fw_port") \
                and this.fields.get(_prop(this.cls, "m_provider")) is None:
            return None
        if isinstance(this, Obj) and (
                (sub.name in _MAP_CALLS and _derives(this.cls, "fw_extern_map"))
                or (sub.name in _FACT_CALLS and _derives(this.cls, "fw_facts"))):
            site = caller.pos[-1] if caller is not None and caller.pos else call_expr
            self.map_calls.setdefault(this.oid, []).append((sub.name, site))
        res = yield from super().call_sub(sub, this, iface, args, caller, call_expr)
        if sub.name == "connect" and isinstance(this, Obj) and args \
                and (_derives(this.cls, "fw_port") or _derives(this.cls, "fw_export")):
            site = caller.pos[-1] if caller is not None and caller.pos else call_expr
            prov = this.fields.get(_prop(this.cls, "m_provider")) \
                if _derives(this.cls, "fw_port") else None
            self.connects.append((this, prov, site))
        return res


#: The fw_extern_map methods whose call sites diagnostics point at.
_MAP_CALLS = ("param", "param_str", "clock", "reset", "rv", "valid", "level", "tie", "open")
#: The fw_facts methods, likewise.
_FACT_CALLS = ("latency", "ii", "capacity", "comb_path", "registered", "area")


class _Top:
    name = "fw_hier"


def elaborate_tree(compilation, top_cls, name: Optional[str] = None) -> Node:
    """Construct *top_cls* as ``new(name, null)`` and run ``do_build`` and
    ``do_connect``; return the tree."""
    name = name or top_cls.name
    it = _Recorder(compilation, _Top())
    fr = Frame(None, None, None)
    o = it.new_object(top_cls)
    ctor = _sub(top_cls, "new")
    it.run_sync(it.call_sub(ctor, o, None, [Val(name), Val(None)], fr, None))
    # fw_root seats the root's clock on a bridge before start(); do the same
    # over a placeholder interface (no thread runs, so it is never read).
    bridge_t = compilation.getPackage("fw_hdl_pkg").find("fw_clock_xtor_bridge")
    clk = it.new_object(bridge_t)
    it.run_sync(it.call_sub(_sub(bridge_t, "new"), clk, None,
                            [Val("clock"), Val(o), Val(Iface(None, f"{name}.u_clk"))], fr, None))
    clock_port = o.fields[_prop(top_cls, "clock")]
    it.run_sync(it.call_sub(_sub(clock_port.cls, "connect"), clock_port, None, [Val(clk)],
                            fr, None))
    rd = _Reader(it)
    it.run_sync(it.call_sub(it._dispatch(o.cls, _sub(top_cls, "do_build")), o, None, [], fr, None))
    missing = rd.unbuilt(o)
    try:
        it.run_sync(it.call_sub(it._dispatch(o.cls, _sub(top_cls, "do_connect")), o, None, [],
                                fr, None))
    except HierError:
        raise
    except ElabError as e:
        # A field build() left null is fine (a child under an `if`) until
        # connect() reaches through it.
        if missing and "null object" in str(e):
            comp, names, where = missing[0]
            raise HierError(f"build() of {comp!r} does not construct {names}", where) from None
        raise
    return rd.node(o, name, name, None, None, None)


class _Reader:
    def __init__(self, it: _Recorder):
        self.it = it

    def _field(self, o: Obj, prop_name: str):
        return o.fields.get(_prop(o.cls, prop_name))

    def _holders(self, o: Obj) -> Dict[int, Tuple[Any, Optional[int]]]:
        """oid -> (property, index) for the objects *o*'s own properties hold."""
        out: Dict[int, Tuple[Any, Optional[int]]] = {}
        c = o.cls
        while c is not None and c.kind == SK.ClassType \
                and _generic(c) not in ("fw_component", "fw_component_param"):
            for m in c:
                if m.kind != SK.ClassProperty:
                    continue
                v = o.fields.get(m)
                if isinstance(v, Obj):
                    out.setdefault(v.oid, (m, None))
                elif isinstance(v, list):
                    for i, x in enumerate(v):
                        if isinstance(x, Obj):
                            out.setdefault(x.oid, (m, i))
            b = c.baseClass
            c = b.canonicalType if b is not None else None
        return out

    def _user_props(self, ct):
        c = ct
        while c is not None and c.kind == SK.ClassType \
                and _generic(c) not in ("fw_component", "fw_component_param"):
            for m in c:
                if m.kind == SK.ClassProperty \
                        and m.lifetime != ast.VariableLifetime.Static:
                    yield m
            b = c.baseClass
            c = b.canonicalType if b is not None else None

    def _site(self, o: Obj, fallback=None):
        return self.it.created.get(o.oid, fallback)

    def _check_name(self, o: Obj, given: str, prop, index, owner_cls) -> str:
        want = prop.name if index is None else (f"{prop.name}[{index}]", f"{prop.name}_{index}")
        ok = given == want if index is None else given in want
        if not ok:
            shown = want if index is None else want[0]
            raise HierError(f"{prop.name if index is None else shown!r} must be constructed as "
                            f"new(\"{shown}\", this): the name becomes the RTL instance name",
                            self._site(o, prop))
        return rtl_name(given)

    def node(self, o: Obj, path: str, name: str, prop, index, decl_type) -> Node:
        cls = o.cls
        n = Node(path=path, name=name, obj=o, cls=cls, prop=prop, index=index,
                 decl_type=decl_type)
        for x in cls:
            if x.kind == SK.TypeParameter:
                n.params[x.name] = str(x.targetType.type)
            elif x.kind == SK.Parameter:
                n.params[x.name] = str(const_to_py(x.value))
        if _derives(cls, "fw_component_param"):
            po = self._field(o, "m_params")
            if isinstance(po, Obj):
                n.param_obj = {m.name: v for m, v in po.fields.items()
                               if isinstance(v, (int, str, bool))}
        n.has_run = _own_sub(cls, "run") is not None or _own_step(cls) is not None
        holders = self._holders(o)
        elab = self._field(o, "m_elab") or []
        for e in elab:
            if not isinstance(e, Obj):
                continue
            h = holders.get(e.oid)
            if _derives(e.cls, "fw_port") or _derives(e.cls, "fw_export"):
                if h is None or not _derives(e.cls, "fw_port"):
                    continue                    # library endpoints (clock, dbg)
                pname = self._field(e, "m_ep_name")
                rname = self._check_name(e, pname, h[0], h[1], cls)
                n.ports[rname] = Port(rname, e, e.cls, h[0], h[1])
            elif _derives(e.cls, "fw_component"):
                if h is None:
                    cname = self._field(e, "m_name")
                    # Built again under the same name: the property holds the later one.
                    later = next((x for x in elab if isinstance(x, Obj) and x.oid in holders
                                  and _derives(x.cls, "fw_component")
                                  and self._field(x, "m_name") == cname), None)
                    if later is not None:
                        raise HierError(f"{cname!r} is constructed twice", self._site(later))
                    raise HierError(f"{path}.{cname}: a child component is not held by a "
                                    f"property of {cls.name}", self._site(e))
                cname = self._field(e, "m_name")
                rname = self._check_name(e, cname, h[0], h[1], cls)
                if rname in n.children or rname in n.channels:
                    raise HierError(f"two children of {cls.name} are both named {rname!r} in RTL",
                                    self._site(e))
                if _channel_class(e.cls) is not None:
                    n.channels[rname] = Channel(rname, e, e.cls, h[0], h[1])
                else:
                    t = h[0].type
                    if h[1] is not None:
                        t = t.canonicalType.arrayElementType if hasattr(
                            t.canonicalType, "arrayElementType") else t
                    n.children[rname] = self.node(e, f"{path}.{rname}", rname, h[0], h[1], t)
        if _implements_extern(cls):
            if n.children:
                raise HierError(f"class {cls.name!r} has children and implements "
                                f"fw_extern_impl; a wrapper is a leaf",
                                _sub(cls, "extern_map"))
            n.extern = self.extern_record(o, n)
        fsub = _declared_sub(cls, "facts")
        if fsub is not None:
            if n.children:
                raise HierError(f"class {cls.name!r} has children and declares facts(); facts "
                                f"describe a leaf (a structural component's come from its "
                                f"children)", fsub)
            n.facts = self.declared_facts(o, n, fsub)
        if n.children:
            self._check_props(n)
            if n.has_run:
                raise HierError(f"class {cls.name!r} has children and a run() task or step(); "
                                f"a component is either structural (build/connect) or a "
                                f"process (run, step), not both",
                                _own_sub(cls, "run") or _own_step(cls))
            self._binds(n)
        return n

    def _call(self, o: Obj, name: str, args=()):
        it = self.it
        fr = Frame(None, None, None)
        return it.run_sync(it.call_sub(it._dispatch(o.cls, _sub(o.cls, name)), o, None,
                                       [Val(a) for a in args], fr, None))

    def extern_record(self, o: Obj, n: Node):
        """Run the wrapper's extern_map() and read what it recorded."""
        from ...extern import Binding, ExternError, ExternRecord
        it = self.it
        map_sub = _sub(o.cls, "extern_map")
        map_t = it.comp.getPackage("fw_hdl_pkg").find("fw_extern_map")
        x = it.new_object(map_t)
        try:
            self._call(o, "extern_map", [x])
            module, fileset = self._call(o, "extern_module"), self._call(o, "extern_fileset")
        except HierError:
            raise
        except ElabError as e:
            raise HierError(f"{n.path}: extern_map(): {e}", map_sub) from None
        f = lambda name: self._field(x, name)                       # noqa: E731
        calls = it.map_calls.get(x.oid, [])
        by: Dict[str, List[Any]] = {}
        for meth, site in calls:
            by.setdefault(meth, []).append(site)
        port_of = {p.obj.oid: name for name, p in n.ports.items()}
        rec = ExternRecord(cls=str(o.cls), module=module, fileset=fileset, site=map_sub)
        names = f("m_param_names") or []
        ints, strs = f("m_param_int") or {}, f("m_param_str") or {}
        psites = by.get("param", []) + by.get("param_str", [])
        for i, pn in enumerate(names):
            if pn in rec.params:
                raise HierError(f"{n.path}: x.param({pn!r}, ...) given twice",
                                psites[i] if i < len(psites) else map_sub)
            rec.params[pn] = strs[pn] if pn in strs else int(ints[pn])
        rec.clock, rec.reset = f("m_clock") or "", f("m_reset") or ""
        rec.reset_active_low = bool(f("m_reset_active_low"))
        for k in ("clock", "reset"):
            if by.get(k):
                rec.sites[k] = by[k][-1]
        bsites = [s for m, s in calls if m in ("rv", "valid", "level")]
        for i, b in enumerate(f("m_binds") or []):
            site = bsites[i] if i < len(bsites) else map_sub
            ep = self._field(b, "ep")
            if not isinstance(ep, Obj):
                raise HierError(f"{n.path}: x.{self._field(b, 'kind')}(...) is given a null "
                                f"port (not built?)", site)
            port = port_of.get(ep.oid)
            if port is None:
                raise HierError(f"{n.path}: x.{self._field(b, 'kind')}(...) is given "
                                f"{self._field(ep, 'm_ep_name')!r}, which is not a port of "
                                f"{o.cls.name}", site)
            rec.bindings.append(Binding(port=port, kind=self._field(b, "kind"),
                                        name=self._field(b, "name"),
                                        style=self._field(b, "style"),
                                        pins=dict(self._field(b, "pins") or {}), site=site))
        tsites, osites = by.get("tie", []), by.get("open", [])
        for i, (pin, v) in enumerate(zip(f("m_tie_pins") or [], f("m_tie_values") or [])):
            rec.ties.append((pin, int(v)))
            if i < len(tsites):
                rec.sites[f"tie:{pin}"] = tsites[i]
        for i, pin in enumerate(f("m_open_pins") or []):
            rec.opens.append(pin)
            if i < len(osites):
                rec.sites[f"open:{pin}"] = osites[i]
        return rec

    def declared_facts(self, o: Obj, n: Node, fsub) -> List[Any]:
        """Run the leaf's facts() and read what it recorded."""
        from ...facts import KINDS, BlockFact, FactsError, check_value
        it = self.it
        x = it.new_object(it.comp.getPackage("fw_hdl_pkg").find("fw_facts"))
        try:
            self._call(o, "facts", [x])
        except HierError:
            raise
        except ElabError as e:
            raise HierError(f"{n.path}: facts(): {e}", fsub) from None
        sites = [s for _, s in it.map_calls.get(x.oid, [])]
        port_of = {p.obj.oid: name for name, p in n.ports.items()}
        fields = {"latency": ("src", "dst"), "capacity": ("src", "dst"),
                  "comb_path": ("src", "dst"), "ii": ("port",), "registered": ("port",),
                  "area": ()}
        out = []
        for i, r in enumerate(self._field(x, "m_facts") or []):
            site = sites[i] if i < len(sites) else fsub
            kind = self._field(r, "kind")
            v: Dict[str, Any] = {}
            for fname, ep in zip(fields[kind], (self._field(r, "a"), self._field(r, "b"))):
                if not isinstance(ep, Obj):
                    raise HierError(f"{n.path}: f.{kind}(...) is given a null port (not built?)",
                                    site)
                port = port_of.get(ep.oid)
                if port is None:
                    raise HierError(f"{n.path}: f.{kind}(...) is given "
                                    f"{self._field(ep, 'm_ep_name')!r}, which is not a port of "
                                    f"{o.cls.name}", site)
                v[fname] = port
            v.update({k: int(val) for k, val in (self._field(r, "n") or {}).items()})
            v.update(dict(self._field(r, "s") or {}))
            f = BlockFact(KINDS[kind], v, site)
            try:
                check_value(f)
            except FactsError as e:
                raise HierError(f"{n.path}: {e}", site) from None
            out.append(f)
        return out

    def unbuilt(self, o: Obj, out=None) -> List[Tuple[str, List[str], Any]]:
        """After do_build: the endpoint and child properties left null, per
        component, as (class, names, build())."""
        out = [] if out is None else out
        names = []
        for m in self._user_props(o.cls):
            ct = m.type.canonicalType
            et = ct.arrayElementType.canonicalType if getattr(ct, "arrayElementType", None) \
                is not None else ct
            if et.kind != SK.ClassType or not (_derives(et, "fw_component")
                                               or _derives(et, "fw_port")):
                continue
            v = o.fields.get(m)
            items = v if isinstance(v, list) else [v]
            names += [m.name if not isinstance(v, list) else f"{m.name}[{i}]"
                      for i, x in enumerate(items) if x is None]
        if names:
            out.append((o.cls.name, names, _own_sub(o.cls, "build") or o.cls))
        for e in self._field(o, "m_elab") or []:
            if isinstance(e, Obj) and _derives(e.cls, "fw_component"):
                self.unbuilt(e, out)
        return out

    def _check_props(self, n: Node) -> None:
        held = {(id(p.prop), p.index) for p in n.ports.values()} | \
            {(id(c.prop), c.index) for c in n.channels.values()} | \
            {(id(c.prop), c.index) for c in n.children.values()}
        for m in self._user_props(n.cls):
            v = n.obj.fields.get(m)
            ct = m.type.canonicalType
            et = ct.arrayElementType.canonicalType if hasattr(ct, "arrayElementType") \
                and ct.arrayElementType is not None else ct
            if et.kind != SK.ClassType or not (_derives(et, "fw_component")
                                               or _derives(et, "fw_port")):
                raise HierError(f"property {m.name!r}: a structural component holds only "
                                f"ports, child components and channels (or arrays of them)", m)
            items = v if isinstance(v, list) else [v]
            for i, x in enumerate(items):
                idx = i if isinstance(v, list) else None
                if x is None:
                    continue                    # not built (a conditional child)
                if (id(m), idx) not in held:
                    raise HierError(f"{m.name}: the object it holds is not a child of "
                                    f"{n.cls.name} (build it with this as its parent)", m)

    def _binds(self, n: Node) -> None:
        own = {p.obj.oid: name for name, p in n.ports.items()}
        ends: Dict[int, Tuple[str, str]] = {}
        for cname, ch in n.channels.items():
            for end in ("put_ex", "put_step_ex", "get_ex", "get_nb_ex"):
                try:
                    v = self._field(ch.obj, end)
                except ElabError:
                    continue
                if isinstance(v, Obj):
                    # put_step_ex (fw_put_step_if) is the same put end in RTL.
                    ends[v.oid] = (cname, "put_ex" if end == "put_step_ex" else end)
        child_ports: Dict[int, Tuple[str, str]] = {}
        for cname, c in n.children.items():
            for pname, p in c.ports.items():
                child_ports[p.obj.oid] = (cname, p.prop.name if p.index is None else pname)
        connect = _own_sub(n.cls, "connect") or n.prop
        used: Dict[str, Any] = {}
        for ep, prov, site in self.it.connects:
            if ep.oid not in child_ports:
                continue
            lname = "%s.%s" % child_ports[ep.oid]
            if prov is None or not isinstance(prov, Obj):
                continue
            if prov.oid in own:
                rname, rkey = own[prov.oid], (own[prov.oid], None)
            elif prov.oid in ends:
                rname, rkey = "%s.%s" % ends[prov.oid], ends[prov.oid]
            elif prov.oid in child_ports:
                raise HierError(f"{'%s.%s' % child_ports[prov.oid]}: the provider must be a "
                                f"channel end or one of {n.cls.name}'s own ports "
                                f"(child-to-child needs a channel)", site)
            else:
                raise HierError(f"{lname} is bound to something outside {n.cls.name}", site)
            for k in (lname, rname):
                if k in used:
                    raise HierError(f"{k} is connected twice; a channel end and a port each "
                                    f"connect exactly once", site)
                used[k] = site
            n.binds.append((child_ports[ep.oid], rkey))
        for cname, c in n.children.items():
            for pname, p in c.ports.items():
                key = f"{cname}.{p.prop.name if p.index is None else pname}"
                if key not in used:
                    raise HierError(f"port {key} is not connected", connect)
        for pname in n.ports:
            if pname not in used:
                raise HierError(f"port {pname} is not connected to a child", connect)
        for cname in n.channels:
            if f"{cname}.put_ex" not in used:
                raise HierError(f"channel end {cname}.put_ex is not connected", connect)
            getters = [e for e in ("get_ex", "get_nb_ex") if f"{cname}.{e}" in used]
            if not getters:
                raise HierError(f"channel end {cname}.get_ex is not connected", connect)
            if len(getters) > 1:
                raise HierError(f"channel {cname} has two consumers (get_ex and get_nb_ex); "
                                f"a channel has exactly one", connect)
