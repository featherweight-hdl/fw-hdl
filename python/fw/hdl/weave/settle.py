"""The settle weaver (design-sync-rtl §4.6.1, mode A; plan S4.2).

For every class that implements ``fw_combinational`` or ``fw_steppable`` and owns
struct ports, it computes the port fields that ``comb()`` and ``step()`` read and
write, and registers an ``fw_settle_table`` for the class from ``<pkg>_woven``,
keyed by the class's qualified name (the generic name for a parameterized class;
the table is the union over its specializations).

The read/write sets come from ``sv_weave.analysis.rw``, stopped at the struct-port
boundary: a call to a method of an ``fw_sync_port`` or ``fw_sig_holder`` class is
not followed. Its effect is the field named by the method's ``fw_reads`` or
``fw_writes`` attribute (``(* fw_reads = "valid" *) function bit get_valid()``),
under the receiver's path; a boundary method with neither attribute is opaque.
Reads and writes of anything else (state) are not part of the table.

For ``comb()`` the table also has the dependences of each written field: the
fields read by the same top-level statement (``o.valid <- i.valid``). They are
the product of all reads and writes when a statement could carry a value to
another: a local, or a member (state) that one statement writes and another
reads. The scheduler uses them to tell a false cycle from a true loop.

Diagnostics: an opaque call in ``comb()`` is an error (its effects are unknown,
so the schedule could be wrong); a ``comb()`` that writes no port field is a
warning (it can never feed another process).
"""
from typing import Dict, List, Optional, Set, Tuple

from sv_weave.analysis.rw import RwSets, analyze, analyze_stmts
from sv_weave.plugin import Weaver

BOUNDARY = ("fw_sync_port", "fw_sig_holder")
PROCS = (("comb", "fw_combinational"), ("step", "fw_steppable"))
_MARK = "@"     # marks a field effect in a summary path, so it survives prefixing


def _q(s: str) -> str:
    return '"%s"' % s


def _split_args(s: str) -> List[str]:
    """Split a parameter list at top-level commas."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()] if cur.strip() else out


def _attr_names(m, key: str) -> Set[str]:
    v = m.attrs.get(key)
    return set(v.split(",")) if isinstance(v, str) and v else set()


class _Boundary:
    """The struct-port classes of a model, and the summary of their methods."""

    def __init__(self, model):
        self.classes = [c for c in model.classes() if any(c.is_a(b) for b in BOUNDARY)]
        self.names = {c.generic.name if c.generic else c.name for c in self.classes}
        self.names.update(BOUNDARY)
        self._by_sym: Dict[int, RwSets] = {}
        for c in self.classes:
            for m in c.methods:
                if m.slang is None or m.is_constructor:
                    continue
                r = {_MARK + f for f in _attr_names(m, "fw_reads")}
                w = {_MARK + f for f in _attr_names(m, "fw_writes")}
                o = set() if (r or w) else {m.name}
                self._by_sym[id(m.slang)] = RwSets(frozenset(r), frozenset(w), frozenset(o))

    def summary(self, callee) -> Optional[RwSets]:
        return self._by_sym.get(id(callee))

    def is_port(self, field) -> bool:
        sp = field.type.spelling or ""
        return sp.split("#")[0].split("::")[-1].strip() in self.names


def _fields(paths) -> List[str]:
    """``in.@valid`` -> ``in.valid``; paths without a field effect are dropped."""
    out = set()
    for p in paths:
        head, sep, f = p.rpartition("." + _MARK)
        if sep:
            out.add(head + "." + f)
    return sorted(out)


class SettleWeaver(Weaver):
    name = "fw_settle"
    version = "0.1"

    def subscribe(self, bus):
        bus.on_design(self.design)

    def design(self, d):
        bnd = _Boundary(d.model)
        # key -> (package, {proc: (reads, writes)}, comb deps {(write, read)})
        tables: Dict[str, Tuple[str, Dict[str, Tuple[Set[str], Set[str]]],
                                Set[Tuple[str, str]]]] = {}
        # key -> {(type, depth)}: the matchers of the comb() classes
        matches: Dict[str, Set[Tuple[str, int]]] = {}
        for c in d.model.classes():
            if c.is_interface or c.package is None:
                continue
            procs = [p for p, iface in PROCS if c.implements_iface(iface)]
            if not procs or not any(bnd.is_port(f) for f in c.all_fields()):
                continue
            key = c.generic.qname if c.generic else c.qname
            _, ent, deps = tables.setdefault(key, (c.package, {}, set()))
            if "comb" in procs:
                ty = self._type(c)
                if ty is None:
                    d.warning("fw_settle: %s has a type argument the woven package cannot "
                              "name; its instances use the naive fallback" % c.qname, c.loc)
                else:
                    matches.setdefault(key, set()).add((ty, len(c.ancestors())))
            for p in procs:
                m = c.find_method(p)
                if m is None or m.pure or m.slang is None:
                    continue
                rw = analyze(m.slang, bnd.summary)
                reads, writes = _fields(rw.reads), _fields(rw.writes)
                if p == "comb":
                    for o in sorted(rw.opaque):
                        d.error("fw_settle: %s.comb() calls %s, whose reads and writes are "
                                "unknown" % (c.qname, o), m.loc)
                    if not writes:
                        d.warning("fw_settle: %s.comb() writes no port field" % c.qname,
                                  m.loc)
                    deps.update(self._deps(m.slang, bnd, reads, writes))
                r, w = ent.setdefault(p, (set(), set()))
                r.update(reads)
                w.update(writes)
        for key in sorted(tables):
            pkg, ent, deps = tables[key]
            d.add_registration(pkg, self._register(key, ent, deps,
                                                   sorted(matches.get(key, ()))))

    @staticmethod
    def _deps(sub, bnd, reads, writes) -> Set[Tuple[str, str]]:
        """(write, read) field pairs of comb() body sub, per top-level statement."""
        stmts = analyze_stmts(sub, bnd.summary)
        if stmts is not None:
            def state(paths):
                return {p for p in paths if "." + _MARK not in p}
            for i, a in enumerate(stmts):
                if any(state(a.writes) & state(b.reads)
                       for j, b in enumerate(stmts) if j != i):
                    stmts = None
                    break
        if stmts is None:
            return {(w, r) for w in writes for r in reads}
        return {(w, r) for s in stmts for w in _fields(s.writes) for r in _fields(s.reads)}

    @staticmethod
    def _type(c) -> Optional[str]:
        """How ``<pkg>_woven`` names c. A type argument that is a typedef outside
        any package (``$unit``, a module) is spelled as its integral type
        (``logic[36:0]``); None if it is not integral. A value argument the
        model can only abbreviate (a wide struct parameter such as fw_proto's
        ``axi4_param_t P``: ``320'd1591...e50``) is named by a typedef of the
        specialization in the generic's package; None if there is none."""
        t = c.type_expr or c.name
        if "..." in t:
            return SettleWeaver._alias(c)
        if c.generic is not None and c.slang is not None and "#" in t:
            vals, local = [], False
            for m in c.slang:
                if m.kind == m.kind.Parameter and m.isPortParam:
                    vals.append(str(m.value))
                elif m.kind == m.kind.TypeParameter and m.isPortParam:
                    a = m.targetType.type
                    if a.isAlias and "::" not in (a.lexicalPath or a.name):
                        if not a.canonicalType.isIntegral:
                            return None
                        local = True
                        vals.append(str(a.canonicalType))
                    else:
                        vals.append(None)
            if local:
                # Splice: keep the model's spelling for every other argument.
                head, args = t.split("#", 1)
                orig = _split_args(args.strip()[1:-1])
                if len(orig) != len(vals):
                    return None
                t = "%s#(%s)" % (head, ", ".join(v if v is not None else o
                                                  for v, o in zip(vals, orig)))
        return t if "::" in t.split("#")[0] else "%s::%s" % (c.package, t)

    @staticmethod
    def _alias(c) -> Optional[str]:
        """``pkg::name`` of a typedef that names c's specialization, in the
        package that declares c's generic class; None if there is none."""
        ct = c.slang
        if ct is None or ct.genericClass is None:
            return None
        scope = ct.genericClass.parentScope
        if scope is None or c.package is None:
            return None
        for m in scope:
            if m.kind == m.kind.TypeAlias and m.targetType.type.canonicalType.isMatching(ct):
                return "%s::%s" % (c.package, m.name)
        return None

    @staticmethod
    def _register(key, ent, deps, matches) -> str:
        lines = ["begin", "  fw_hdl_pkg::fw_settle_table t = new(%s);" % _q(key)]
        for ty, depth in matches:
            lines += ["  begin",
                      "    fw_hdl_pkg::fw_settle_is #(%s) m = new(%d);" % (ty, depth),
                      "    t.matchers.push_back(m);",
                      "  end"]
        for p in ("comb", "step"):
            if p not in ent:
                continue
            for kind, names in zip(("reads", "writes"), ent[p]):
                for n in sorted(names):
                    lines.append("  t.%s_%s.push_back(%s);" % (p, kind, _q(n)))
        if "comb" in ent:
            lines.append("  t.deps_known = 1;")
            for w, r in sorted(deps):
                lines.append("  t.comb_dep(%s, %s);" % (_q(w), _q(r)))
        lines += ["  fw_hdl_pkg::fw_settle_table::add(t);", "end"]
        return "\n".join(lines)
