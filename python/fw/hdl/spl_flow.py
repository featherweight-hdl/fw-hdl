"""SPL sources -> an integrated RTL top, with XLS implementing chosen blocks
(``xls-phase2.md``).

The three steps, as plain functions (the dv-flow tasks wrap these):

* :func:`partition` (A): read the top's structure, check that every child is
  assigned to an engine (X2: XLS only), and map each assigned class with the
  static-subset front end. Errors point at SV lines.
* :func:`xls_block` (B): one class -> XLS IR -> ``codegen_main`` -> a Verilog
  module plus its *actual* signature (checked against the prediction).
* :func:`integrate` (C): a structural top built from the signatures alone
  (Rule 1): one instance per child, a FIFO per channel (``fw_rv_fifo``, or
  what the channel's storage binding names: :mod:`fw.hdl.storage`), and the top's
  own channels as ready/valid pins. It also returns the top's signature, so a
  composed top is itself a block.
"""
from __future__ import annotations

import dataclasses as dc
import json
import re
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

import zuspec.ir.core as ir
from zuspec.ir.core import RecognitionError

from . import ir_build as _b
from . import native
from .lib import registry as librg
from .config import FlowConfig
from .emit.be_sv import emit_sv
from .errors import Diagnostic, ErrorReporter, FwHdlError, Severity
from .fe.static_mapper import StaticMapper
from .fe.structure import Structure, StructureMapper
from .xls_flow import XlsFlowError, _find_class, _parse

#: The library module a channel becomes (src/rtl/fw_rv_fifo.sv).
FIFO_MODULE = "fw_rv_fifo"
#: The credit checker on a valid-only channel (src/rtl/fw_valid_check.sv).
VALID_CHECK_MODULE = "fw_valid_check"

#: The pins of each channel kind, and its block-signature flow control.
KIND_ROLES = {"ready_valid": ("data", "valid", "ready"), "valid": ("data", "valid"),
              "level": ("data",)}
_FLOW_OF_KIND = {"ready_valid": "ready_valid", "valid": "valid", "level": "none"}


def channel_kind(ch: ir.ChannelSignature) -> str:
    """A signature channel's kind: ``valid`` (the producer has no use for
    ready), ``level`` (data only) or ``ready_valid``."""
    if ch.flow_control == "valid":
        return "valid"
    if ch.flow_control == "none" and "valid" not in ch.ports:
        return "level"
    return "ready_valid"


@dc.dataclass
class Partition:
    """The manifest and the shell (A's output)."""
    structure: Structure
    #: class spelling -> its static-subset IR, one per class (not per instance)
    blocks: Dict[str, ir.DataTypeComponent]
    shell: Shell
    #: group name -> its shell entry's ``group`` (one multi-proc block)
    groups: Dict[str, dict] = dc.field(default_factory=dict)
    #: block spelling -> what a knob file may call it (see :func:`_names`)
    names: Dict[str, List[str]] = dc.field(default_factory=dict)
    #: class spelling -> a native child (``native.RegChild``), one per class
    natives: Dict[str, object] = dc.field(default_factory=dict)
    #: class spelling -> XLS IR text, for a class the registry lowers;
    #: its ``blocks`` entry then holds only its ports
    texts: Dict[str, str] = dc.field(default_factory=dict)

    def knob_key(self, spelling: str, known: Sequence[str]) -> str:
        """The name the knob file uses for block *spelling*: the first of its
        names in *known* (the knob file's blocks), else the spelling."""
        return next((n for n in self.names.get(spelling, []) if n in known), spelling)

    def standalone(self) -> Dict[str, ir.DataTypeComponent]:
        """The blocks that are generated on their own (not only inside a group)."""
        used = {c["class"] for sh in self.shell.walk() for c in sh.children
                if c.get("engine") == "xls" and "group" not in c}
        return {k: v for k, v in self.blocks.items() if k in used}

    def group_text(self, name: str) -> str:
        """The multi-proc XLS package for group *name*."""
        from zuspec.be.xls.multi_proc import lower_group
        g = self.groups[name]
        members = [(m["name"], self.blocks[m["class"]], m["module"]) for m in g["members"]]
        return lower_group(module_name(name), members, g["internal"], g["external"])

    def group_component(self, name: str) -> ir.DataTypeComponent:
        from zuspec.be.xls.multi_proc import group_component
        g = self.groups[name]
        return group_component(module_name(name),
                               {m["name"]: self.blocks[m["class"]] for m in g["members"]},
                               g["external"])


def module_name(spelling: str) -> str:
    """The generated module's name for a class spelling (BLK-3): stable, and
    a legal identifier (`pkg::cls` -> `pkg__cls`)."""
    return re.sub(r"\W", "_", spelling.replace("::", "__"))


@dc.dataclass
class Shell:
    """What integration needs from the top component, and nothing else: its
    pins, channels, children and binds (``splPartition`` file, xls-phase2.md §3.1).

    ``ports`` and ``channels`` hold dicts with ``name``, ``bits``, ``sv_type``
    and, respectively, ``direction`` ("in"/"out") or ``depth``. A child is
    ``{name, class, module, engine, alias}``; ``engine`` is the child's kind:

    * ``xls``: a class XLS implements (one block per distinct class);
    * ``structural``: a component with children of its own, whose shell is
      nested under ``shell`` and which integrates to a module of its own;
    * ``extern``: RTL supplied with the design, ``extern: {signature, module,
      files}`` (knob ``design.extern``);
    * ``native``: RTL fw-hdl emits itself (:mod:`fw.hdl.native`), ``native:
      {kind, ...}``; a register-block child (``fw_reg_component``) is one.
      Once written to files it also has ``signature`` and ``files``, as an
      extern child.

    A bind is ``{"port": [child, port], "provider": [name, end]}``, where ``end``
    is ``put_ex``/``get_ex``/``get_nb_ex`` for a channel and None for one of the
    top's own ports. Version 1 files (no nesting, no extern) still load."""
    top: str
    module: str
    ports: List[dict] = dc.field(default_factory=list)
    channels: List[dict] = dc.field(default_factory=list)
    children: List[dict] = dc.field(default_factory=list)
    binds: List[dict] = dc.field(default_factory=list)

    FORMAT: ClassVar[str] = "fw-hdl.spl-partition"
    VERSION: ClassVar[int] = 2

    def to_json(self) -> dict:
        return {"format": self.FORMAT, "version": self.VERSION, **dc.asdict(self)}

    @classmethod
    def from_json(cls, d: dict) -> "Shell":
        if d.get("format") != cls.FORMAT or d.get("version") not in (1, cls.VERSION):
            raise ValueError(f"not an {cls.FORMAT} v1/v{cls.VERSION} file")
        return cls(**{f.name: d[f.name] for f in dc.fields(cls)})

    def nested(self, child: dict) -> "Shell":
        """A structural child's own shell."""
        return Shell(**child["shell"])

    def walk(self):
        """This shell and every nested one, parents first."""
        yield self
        for c in self.children:
            if c.get("engine") == "structural":
                yield from self.nested(c).walk()

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_json(), f, indent=2)
            f.write("\n")

    @classmethod
    def load(cls, path: str) -> "Shell":
        with open(path) as f:
            return cls.from_json(json.load(f))


def _shell(st: Structure, engines: Optional[Dict[str, dict]] = None) -> Shell:
    """*engines*: child spelling -> ``{"engine": ..., "extern": ...}``
    (default: every leaf is ``xls``)."""
    engines = engines or {}
    comp = st.component
    sh = Shell(top=comp.name, module=module_name(comp.name))
    for f in comp.fields:
        if f.kind == ir.FieldKind.Port:
            sh.ports.append({"name": f.name,
                             "direction": "in" if isinstance(f.datatype, ir.DataTypeGetIF) else "out",
                             "bits": f.datatype.element_type.bits,
                             "sv_type": f.pragmas.get("sv_type"),
                             "kind": f.pragmas.get("fw_flow", "ready_valid")})
        elif isinstance(f.datatype, ir.DataTypeChannel):
            sh.channels.append({"name": f.name, "bits": f.datatype.element_type.bits,
                                "depth": f.datatype.depth, "sv_type": f.pragmas.get("sv_type"),
                                "kind": f.pragmas.get("fw_kind", "ready_valid")})
    for c in st.children.values():
        e = {"name": c.name, "class": c.spelling, "module": module_name(c.spelling),
             "engine": "xls", "alias": c.alias}
        if c.structure is None:
            # A class that holds storage in its own state (knob `storage:`).
            sk = librg.storage_kind(c.cls)
            if sk is not None:
                e["holds"] = {"bindings": list(sk.bindings), "why": sk.why}
        if c.structure is not None:
            e["engine"] = "structural"
            e["shell"] = dc.asdict(_shell(c.structure, engines))
        elif c.spelling in engines:
            e.update(engines[c.spelling])
            if e.get("extern", {}).get("module"):
                e["module"] = e["extern"]["module"]
        sh.children.append(e)
    for b in comp.bind_map:
        sh.binds.append({"port": list(_path_name(comp, b.lhs)),
                         "provider": list(_path_name(comp, b.rhs))})
    return sh


def _names(c) -> List[str]:
    """What an engine assignment or a group may call a child: its block
    spelling, its SV class as written (``add_k#(1)``), or its generic class
    (every specialization of it)."""
    out = [c.spelling, str(c.cls).replace(" ", ""), c.cls.name]
    g = getattr(c.cls, "genericClass", None)
    if g is not None:
        out.append(g.name)
    return out


def partition(files: Sequence[str], top: str, xls: Sequence[str],
              config: Optional[FlowConfig] = None,
              reporter: Optional[ErrorReporter] = None,
              extern: Optional[Dict[str, dict]] = None,
              groups: Optional[Dict[str, List[str]]] = None) -> Partition:
    """Read *top*'s tree. Every leaf child is either in *xls* (a class XLS
    implements) or in *extern* (class -> ``{signature, module, files}``: RTL
    supplied with the design); a child with children is structural and
    partitioned the same way, recursively. *groups* (knob ``island.groups``:
    name -> classes) makes the XLS children of those classes in one shell one
    multi-proc block."""
    config = config or FlowConfig()
    reporter = reporter or ErrorReporter()
    extern = dict(extern or {})
    parser = _parse(files, config, reporter)
    sm = StructureMapper(config, reporter, parser.source_manager)
    st = sm.map_structure(_find_class(parser, top), spelling=top)
    leaves = list(_leaves(st))
    used = {n for c in leaves for n in _names(c)}
    for what, names in (("XLS", xls), ("extern", extern)):
        unused = [x for x in names if x not in used]
        if unused:
            raise XlsFlowError(f"{unused} assigned to {what} but not instantiated in {top}; "
                               f"its leaf children are {sorted(used)}")
    blocks: Dict[str, ir.DataTypeComponent] = {}
    engines: Dict[str, dict] = {}
    natives: Dict[str, object] = {}
    texts: Dict[str, str] = {}
    for c in leaves:
        # An extern assignment wins (RTL supplied for a library class, say);
        # then the registry; then the static subset.
        ext = next((extern[n] for n in _names(c) if n in extern), None)
        if ext is not None:
            engines[c.spelling] = {"engine": "extern", "extern": dict(ext)}
            continue
        try:
            nat = librg.recognize(c.cls, "native")
            zs = librg.recognize(c.cls, "zuspec") if nat is None else None
            hit = librg.recognize(c.cls, "xls") if nat is None and zs is None else None
        except (RecognitionError, librg.SubclassError) as e:
            raise sm.fail(f"child {c.name!r}: {e}", getattr(e, "node", None) or c.decl) from None
        if nat is not None:
            if c.spelling not in natives:
                try:
                    natives[c.spelling] = native.reg_child(c, module_name(c.spelling))
                except native.NativeError as e:
                    raise sm.fail(str(e), c.decl) from None
            engines[c.spelling] = {"engine": "native", "native": natives[c.spelling].to_json()}
            continue
        if zs is not None:
            # Zuspec IR from the entry's factory: lowered like a mapped class.
            if c.spelling not in blocks:
                blocks[c.spelling] = zs.lowering.component(zs.params, c.spelling,
                                                           dict(c.ports))
            engines[c.spelling] = {"engine": "xls", "recognized": zs.entry.name}
            continue
        if hit is not None:
            if c.spelling not in blocks:
                low = hit.lowering
                fields = [c.ports[p] for p in low.ports(hit.params)]
                blocks[c.spelling] = ir.DataTypeComponent(name=c.spelling, super=None,
                                                          fields=fields)
                texts[c.spelling] = low.text(hit.params, module_name(c.spelling))
            engines[c.spelling] = {"engine": "xls", "recognized": hit.entry.name}
            continue
        if not any(n in xls for n in _names(c)):
            raise sm.fail(f"child {c.name!r} ({c.spelling}) is not assigned to an engine; "
                          f"list it in `xls`, or as an extern block (knob design.extern)",
                          c.decl)
        if c.spelling not in blocks:
            blocks[c.spelling] = StaticMapper(config, reporter, parser.source_manager) \
                .map_component(c.cls, spelling=c.spelling, param_values=c.param_values)
    _check_step_wires(st, blocks, reporter)
    shell = _shell(st, engines)
    names = {c.spelling: _names(c) for c in leaves}
    found: Dict[str, dict] = {}
    for sh in list(shell.walk()):
        found.update(_apply_groups(sh, groups or {}, names, found))
    missing = [g for g in (groups or {}) if g not in found]
    if missing:
        raise XlsFlowError(f"island.groups {missing}: no XLS child of {top} is of their classes")
    for g, entry in found.items():
        bad = [m["name"] for m in entry["members"] if m["class"] in texts]
        if bad:
            raise XlsFlowError(f"island.groups {g}: {bad} are library classes the registry "
                               f"lowers; they cannot join a multi-proc group yet")
    return Partition(st, blocks, shell, found, names, natives, texts)


def _check_step_wires(st: Structure, blocks: Dict[str, ir.DataTypeComponent],
                      reporter: ErrorReporter) -> None:
    """A step may not be an end of a DEPTH 0 channel. Its RTL is a wire, so
    a value would move in the cycle it is put; the class model cannot show
    that, since steps at one edge do not see each other's puts."""
    comp = st.component
    chans = {f.name: f for f in comp.fields
             if isinstance(f.datatype, ir.DataTypeChannel) and f.datatype.depth == 0}
    for b in comp.bind_map:
        (child, port), (name, end) = _path_name(comp, b.lhs), _path_name(comp, b.rhs)
        c = st.children.get(child)
        blk = blocks.get(c.spelling) if c is not None and c.structure is None else None
        if name not in chans or end is None or blk is None:
            continue
        if any(p.metadata.get("fw_step") for p in getattr(blk, "proc_processes", None) or []):
            loc = chans[name].loc
            d = Diagnostic(Severity.ERROR,
                           f"channel {name!r} has DEPTH 0 (a wire), and {child}.{port} is a "
                           f"step's port; a step needs a channel of DEPTH 1 or more",
                           file=loc.file if loc else None, line=loc.line if loc else None,
                           column=loc.pos if loc else None)
            reporter.diagnostics.append(d)
            raise FwHdlError(d)
    for c in st.children.values():
        if c.structure is not None:
            _check_step_wires(c.structure, blocks, reporter)


def _apply_groups(sh: Shell, groups: Dict[str, List[str]], names: Dict[str, List[str]],
                  done: Dict[str, dict]) -> Dict[str, dict]:
    """Rewrite *sh* so each group's members are one child. A channel
    with both ends on members goes inside; every other member port becomes a
    port of the group named ``<instance>_<port>``."""
    out: Dict[str, dict] = {}
    for g, classes in groups.items():
        members = [c for c in sh.children if c.get("engine") == "xls" and "group" not in c
                   and any(n in classes for n in names.get(c["class"], []))]
        if not members:
            continue
        if g in done or g in out:
            raise XlsFlowError(f"island.groups.{g}: its classes are in more than one "
                               f"structural component; a group is one shell's children")
        if any(c["name"] == g for c in sh.children) or any(ch["name"] == g for ch in sh.channels):
            raise XlsFlowError(f"island.groups.{g}: {sh.top} already has a child or channel "
                               f"named {g!r}")
        mnames = {c["name"] for c in members}
        ends: Dict[str, Dict[str, Tuple[str, str]]] = {}
        for b in sh.binds:
            (child, port), (name, end) = b["port"], b["provider"]
            if end is not None:
                ends.setdefault(name, {})["put" if end == "put_ex" else "get"] = (child, port)
        inside = {n for n, e in ends.items()
                  if len(e) == 2 and e["put"][0] in mnames and e["get"][0] in mnames}
        chans = {c["name"]: c for c in sh.channels}
        for n in inside:
            if chans[n].get("kind", "ready_valid") != "ready_valid":
                raise XlsFlowError(f"island.groups.{g}: channel {n} is a "
                                   f"{chans[n]['kind']} channel; a group carries streams only")
        internal = [{"name": n, "depth": chans[n]["depth"], "bits": chans[n]["bits"],
                     "a": list(ends[n]["put"]),
                     "b": list(ends[n]["get"])} for n in sorted(inside)]
        external, binds = [], []
        for b in sh.binds:
            (child, port), prov = b["port"], b["provider"]
            if child not in mnames:
                binds.append(b)
            elif prov[1] is not None and prov[0] in inside:
                continue
            else:
                alias = f"{child}_{port}"
                external.append({"name": alias, "inst": child, "port": port})
                binds.append({"port": [g, alias], "provider": prov})
        entry = {"members": [{"name": c["name"], "class": c["class"], "module": c["module"]}
                             for c in members],
                 "internal": internal, "external": external}
        first = sh.children.index(members[0])
        rest = [c for c in sh.children if c["name"] not in mnames]
        rest.insert(min(first, len(rest)), {"name": g, "class": g, "module": module_name(g),
                                            "engine": "xls", "alias": f"group {g}",
                                            "group": entry})
        sh.children = rest
        sh.channels = [c for c in sh.channels if c["name"] not in inside]
        sh.binds = binds
        out[g] = entry
    return out


def _leaves(st: Structure):
    for c in st.children.values():
        if c.structure is not None:
            yield from _leaves(c.structure)
        else:
            yield c


@dc.dataclass
class Block:
    """B's output for one class."""
    signature: ir.BlockSignature
    verilog: str


def xls_group_block(part: Partition, name: str, stages: int = 1) -> Block:
    """A group's multi-proc package -> one module."""
    from zuspec.be.xls.signature import CodegenOptions, actual_signature, predict_signature
    from zuspec.be.xls.testing.xlstools import run_codegen
    from . import storage
    opts = CodegenOptions(module_name=module_name(name))
    res = run_codegen(part.group_text(name), opts, stages=stages,
                      extra=storage.group_flags(part.groups[name]))
    sig = actual_signature(predict_signature(part.group_component(name), opts), res.signature,
                           sources=[f"{opts.module_name}.sv"])
    return Block(sig, res.verilog)


def xls_block(comp: ir.DataTypeComponent, stages: int = 1,
              opts=None, text: Optional[str] = None) -> Block:
    """XLS IR -> ``opt_main`` -> ``codegen_main`` for one class. *text* is the
    IR when the registry lowers the class (``Partition.texts``)."""
    from zuspec.be.xls.lower_proc import codegen_flags, lower_component
    from zuspec.be.xls.printer import format_package
    from zuspec.be.xls.signature import CodegenOptions, actual_signature, predict_signature
    from zuspec.be.xls.testing.xlstools import run_codegen
    opts = opts or CodegenOptions(module_name=module_name(comp.name))
    extra: List[str] = []
    if text is None:
        pkg = lower_component(comp)
        text, extra = format_package(pkg), codegen_flags(comp, pkg)
    res = run_codegen(text, opts, stages=stages, extra=extra)
    sig = actual_signature(predict_signature(comp, opts), res.signature,
                           sources=[f"{opts.module_name}.sv"])
    return Block(sig, res.verilog)


def _path_name(comp: ir.DataTypeComponent, e: ir.Expr) -> Tuple[str, Optional[str]]:
    if isinstance(e, ir.ExprAttribute):
        return comp.fields[e.value.index].name, e.attr
    return comp.fields[e.index].name, None


def _fifo(c: dict, clock: str, reset: str, instances: List[ir.ModuleInstance]
          ) -> List[ir.Field]:
    """The FIFO for channel *c*, by its storage binding (:mod:`fw.hdl.storage`):
    ``fw_rv_fifo``, a wrapper module with its ports, or ``fw_sram_fifo`` with
    its RAM beside it on nets ``<ch>_ram_*``. Returns the nets it adds."""
    from . import storage
    n, w, depth = c["name"], c["bits"], c["depth"]
    s = c.get("storage") or {"bind": "flops"}
    module = s["module"] if s["bind"] == "wrapper" else storage.FIFO_MODULES[s["bind"]]
    conns = [("clk", clock), ("rst", reset),
             ("in_data", f"{n}_in"), ("in_vld", f"{n}_in_vld"), ("in_rdy", f"{n}_in_rdy"),
             ("out_data", f"{n}_out"), ("out_vld", f"{n}_out_vld"), ("out_rdy", f"{n}_out_rdy")]
    fields: List[ir.Field] = []
    if s["bind"] == "sram":
        aw = max(1, (depth - 2).bit_length())          # $clog2(DEPTH - 1), at least 1
        ram = [("wa", aw), ("we", 1), ("wd", w), ("ra", aw), ("re", 1), ("rd", w)]
        fields = [ir.Field(name=f"{n}_ram_{p}", datatype=ir.DataTypeInt(bits=b, signed=False))
                  for p, b in ram]
        conns += [(f"ram_{p}", f"{n}_ram_{p}") for p, _ in ram]
        instances.append(ir.ModuleInstance(
            module=s["macro"], name=f"{n}_ram",
            parameters={"WIDTH": str(w), "WORDS": str(depth - 1)},
            connections=[ir.PortConnection(port="clk", signal=clock)]
            + [ir.PortConnection(port=p, signal=f"{n}_ram_{p}") for p, _ in ram]))
    instances.append(ir.ModuleInstance(
        module=module, name=n, parameters={"WIDTH": str(w), "DEPTH": str(depth)},
        connections=[ir.PortConnection(port=p, signal=sg) for p, sg in conns]))
    return fields


def integrate(shell: Shell, sigs: Dict[str, ir.BlockSignature],
              top_name: Optional[str] = None, clock: str = "clk",
              reset: str = "rst",
              nested: Optional[List[Tuple[ir.DataTypeComponent, ir.BlockSignature]]] = None
              ) -> Tuple[ir.DataTypeComponent, ir.BlockSignature]:
    """The structural top for *shell*, from the blocks' signatures (keyed by
    module name). Returns the top's IR and its own signature. A structural
    child integrates first, to a module of its own; those modules (innermost
    first) are appended to *nested*."""
    top_name = top_name or shell.module
    nested = [] if nested is None else nested
    sigs = dict(sigs)
    for c in shell.children:
        if c.get("engine") == "structural" and c["module"] not in sigs:
            sub, sub_sig = integrate(shell.nested(c), sigs, top_name=c["module"], clock=clock,
                                     reset=reset, nested=nested)
            nested.append((sub, sub_sig))
            sigs[sub_sig.name] = sub_sig
    u1 = lambda: ir.DataTypeInt(bits=1, signed=False)  # noqa: E731
    fields: List[ir.Field] = [ir.FieldInOut(name=clock, datatype=u1(), is_out=False),
                              ir.FieldInOut(name=reset, datatype=u1(), is_out=False)]
    top_sig = ir.BlockSignature(name=top_name, clock=clock, reset=reset, engine="structural")

    # Own ports -> pins (INT-3), by kind: a stream is <p>, <p>_vld, <p>_rdy; a
    # valid-only output has no ready; a level is <p> alone.
    # nets[(name, end)] = (kind, {role: signal}); a valid-only producer's ready
    # is the constant 1'b1.
    nets: Dict[Tuple[str, Optional[str]], Tuple[str, Dict[str, str]]] = {}
    for p in shell.ports:
        n, w, inbound = p["name"], p["bits"], p["direction"] == "in"
        kind = p.get("kind", "ready_valid")
        if kind == "valid" and inbound:
            raise XlsFlowError(f"port {n}: a valid-only port is an output (fw_valid_put_if)")
        roles = {"data": n, "valid": f"{n}_vld", "ready": f"{n}_rdy"}
        pins = {r: roles[r] for r in KIND_ROLES[kind]}
        for role, sig_name in pins.items():
            fields.append(ir.FieldInOut(
                name=sig_name, datatype=ir.DataTypeInt(bits=w, signed=False) if role == "data"
                else u1(), is_out=(not inbound) if role != "ready" else inbound))
        nets[(n, None)] = (kind, {**pins, **({"ready": "1'b1"} if kind == "valid" else {})})
        top_sig.channels.append(ir.ChannelSignature(
            name=n, direction=p["direction"], payload=ir.DataTypeInt(bits=w, signed=False),
            flow_control=_FLOW_OF_KIND[kind], ports=pins, payload_sv_type=p.get("sv_type")))

    # Channels: a stream or valid-only channel is an fw_rv_fifo with nets
    # <ch>_in* and <ch>_out* (valid-only also gets an fw_valid_check); a level
    # is one net <ch>.
    instances: List[ir.ModuleInstance] = []
    for c in shell.channels:
        n, w = c["name"], c["bits"]
        kind = c.get("kind", "ready_valid")
        if kind == "level":
            fields.append(ir.Field(name=n, datatype=ir.DataTypeInt(bits=w, signed=False)))
            nets[(n, "put_ex")] = nets[(n, "get_ex")] = ("level", {"data": n})
            continue
        for side in ("in", "out"):
            fields += [ir.Field(name=f"{n}_{side}", datatype=ir.DataTypeInt(bits=w, signed=False)),
                       ir.Field(name=f"{n}_{side}_vld", datatype=u1()),
                       ir.Field(name=f"{n}_{side}_rdy", datatype=u1())]
        put = {"data": f"{n}_in", "valid": f"{n}_in_vld", "ready": f"{n}_in_rdy"}
        if kind == "valid":
            put["ready"] = "1'b1"
            instances.append(ir.ModuleInstance(
                module=VALID_CHECK_MODULE, name=f"{n}_chk", parameters={"NAME": f'"{n}"'},
                connections=[ir.PortConnection(port=pp, signal=sg) for pp, sg in [
                    ("clk", clock), ("rst", reset), ("vld", f"{n}_in_vld"),
                    ("rdy", f"{n}_in_rdy")]]))
        nets[(n, "put_ex")] = (kind, put)
        nets[(n, "get_ex")] = ("ready_valid",
                               {"data": f"{n}_out", "valid": f"{n}_out_vld", "ready": f"{n}_out_rdy"})
        # A polling consumer sees the same pins: its non-blocking receive is
        # still a ready/valid transfer, taken only when valid.
        nets[(n, "get_nb_ex")] = nets[(n, "get_ex")]
        fields += _fifo(c, clock, reset, instances)

    # Children -> one instance each, wired by the binds; a port's kind must
    # be its end's.
    provider = {tuple(b["port"]): tuple(b["provider"]) for b in shell.binds}
    for c in shell.children:
        sig = sigs.get(c["module"])
        if sig is None:
            raise XlsFlowError(f"no block signature for {c['name']} (module {c['module']!r})")
        conns = [ir.PortConnection(port=sig.clock, signal=clock)]
        if sig.reset:
            conns.append(ir.PortConnection(port=sig.reset, signal=reset))
        for ch in sig.channels:
            prov = provider.get((c["name"], ch.name))
            if prov is None:
                raise XlsFlowError(f"{c['name']}.{ch.name}: in {sig.name}'s signature but "
                                   f"not bound in {shell.top}")
            net_kind, net = nets[prov]
            kind = channel_kind(ch)
            if kind != net_kind:
                end = prov[0] if prov[1] is None else f"{prov[0]}.{prov[1]}"
                raise XlsFlowError(f"{c['name']}.{ch.name} is a {kind} port ({sig.name}) but "
                                   f"is bound to {end}, a {net_kind} end")
            for role, pin in ch.ports.items():
                sig_name = net.get(role)
                if sig_name is None and role == "ready" and kind == "valid":
                    sig_name = "1'b1"
                if sig_name is None:
                    raise XlsFlowError(f"{c['name']}.{ch.name}: no {role} net for it")
                conns.append(ir.PortConnection(port=pin, signal=sig_name))
        instances.append(ir.ModuleInstance(module=sig.name, name=c["name"], connections=conns))

    top = ir.DataTypeComponent(name=top_name, super=None, fields=fields,
                               module_instances=instances)
    return top, top_sig


@dc.dataclass
class RtlDesign:
    """Everything step C hands to simulation or synthesis."""
    top: str
    files: Dict[str, str]           # file name -> SV text (blocks and the top)
    signature: ir.BlockSignature    # the top's
    block_signatures: Dict[str, ir.BlockSignature]


def spl_to_rtl(files: Sequence[str], top: str, xls: Sequence[str], stages: int = 1,
               config: Optional[FlowConfig] = None,
               reporter: Optional[ErrorReporter] = None,
               extern: Optional[Dict[str, dict]] = None,
               groups: Optional[Dict[str, List[str]]] = None,
               storage: Optional[dict] = None) -> RtlDesign:
    """A -> B for each XLS class -> C, in one call. *storage* is the knob
    ``storage:`` (:mod:`fw.hdl.storage`)."""
    from . import storage as _storage
    part = partition(files, top, xls, config, reporter, extern=extern, groups=groups)
    _storage.plan(part.shell, storage)
    sigs: Dict[str, ir.BlockSignature] = {}
    out: Dict[str, str] = {}
    blocks = [xls_block(comp, stages=stages, text=part.texts.get(k))
              for k, comp in part.standalone().items()]
    blocks += [xls_group_block(part, g, stages=stages) for g in part.groups]
    blocks += native_blocks(part)
    for blk in blocks:
        sigs[blk.signature.name] = blk.signature
        out[blk.signature.sources[0]] = blk.verilog
    sigs.update(extern_signatures(part.shell))
    nested: List[Tuple[ir.DataTypeComponent, ir.BlockSignature]] = []
    top_comp, top_sig = integrate(part.shell, sigs, nested=nested)
    for comp, sig in nested + [(top_comp, top_sig)]:
        sig.sources = [f"{sig.name}.sv"]
        out[sig.sources[0]] = emit_sv(_b.context([comp]))
        sigs[sig.name] = sig
    return RtlDesign(top_sig.name, out, top_sig, sigs)


def native_blocks(part: Partition) -> List[Block]:
    """One module per native class."""
    out = []
    for rc in part.natives.values():
        sig, text = native.reg_child_rtl(rc)
        out.append(Block(sig, text))
    return out


def extern_signatures(shell: Shell) -> Dict[str, ir.BlockSignature]:
    """The signatures of every extern child (at any depth), by module name,
    and of every native child already written to files. A signature's
    ``sources`` default to the entry's ``files``."""
    out: Dict[str, ir.BlockSignature] = {}
    for sh in shell.walk():
        for c in sh.children:
            ext = c.get(c.get("engine")) if c.get("engine") in ("extern", "native") else None
            if not ext or "signature" not in ext:
                continue
            sig = ir.load_signature(ext["signature"])
            if sig.name != c["module"]:
                raise XlsFlowError(f"{c['engine']} child {c['name']}: signature {ext['signature']} "
                                   f"names module {sig.name!r}, expected {c['module']!r}")
            if ext.get("files"):
                sig.sources = list(ext["files"])
            out[sig.name] = sig
    return out
