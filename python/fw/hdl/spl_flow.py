"""SPL sources -> an integrated RTL top, with XLS implementing chosen blocks
(``xls-phase2.md``).

The three steps, as plain functions (the dv-flow tasks wrap these):

* :func:`partition` (A): read the top's structure, check that every child is
  assigned to an engine (X2: XLS only), and map each assigned class with the
  static-subset front end. Errors point at SV lines.
* :func:`xls_block` (B): one class -> XLS IR -> ``codegen_main`` -> a Verilog
  module plus its *actual* signature (checked against the prediction).
* :func:`integrate` (C): a structural top built from the signatures alone
  (Rule 1): one instance per child, an ``fw_rv_fifo`` per channel, and the top's
  own channels as ready/valid pins. It also returns the top's signature, so a
  composed top is itself a block.
"""
from __future__ import annotations

import dataclasses as dc
import json
import re
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

import zuspec.ir.core as ir

from . import ir_build as _b
from .config import FlowConfig
from .emit.be_sv import emit_sv
from .errors import ErrorReporter
from .fe.static_mapper import StaticMapper
from .fe.structure import Structure, StructureMapper
from .xls_flow import XlsFlowError, _find_class, _parse

#: The library module a channel becomes (src/rtl/fw_rv_fifo.sv).
FIFO_MODULE = "fw_rv_fifo"


@dc.dataclass
class Partition:
    """The manifest and the shell (A's output)."""
    structure: Structure
    #: class spelling -> its static-subset IR, one per class (not per instance)
    blocks: Dict[str, ir.DataTypeComponent]
    shell: Shell


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
    ``{name, class, module, engine}``. A bind is ``{"port": [child, port],
    "provider": [name, end]}``, where ``end`` is ``put_ex``/``get_ex`` for a
    channel and None for one of the top's own ports."""
    top: str
    module: str
    ports: List[dict] = dc.field(default_factory=list)
    channels: List[dict] = dc.field(default_factory=list)
    children: List[dict] = dc.field(default_factory=list)
    binds: List[dict] = dc.field(default_factory=list)

    FORMAT: ClassVar[str] = "fw-hdl.spl-partition"
    VERSION: ClassVar[int] = 1

    def to_json(self) -> dict:
        return {"format": self.FORMAT, "version": self.VERSION, **dc.asdict(self)}

    @classmethod
    def from_json(cls, d: dict) -> "Shell":
        if d.get("format") != cls.FORMAT or d.get("version") != cls.VERSION:
            raise ValueError(f"not an {cls.FORMAT} v{cls.VERSION} file")
        return cls(**{f.name: d[f.name] for f in dc.fields(cls)})

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_json(), f, indent=2)
            f.write("\n")

    @classmethod
    def load(cls, path: str) -> "Shell":
        with open(path) as f:
            return cls.from_json(json.load(f))


def _shell(st: Structure, engine: str = "xls") -> Shell:
    comp = st.component
    sh = Shell(top=comp.name, module=module_name(comp.name))
    for f in comp.fields:
        if f.kind == ir.FieldKind.Port:
            sh.ports.append({"name": f.name,
                             "direction": "in" if isinstance(f.datatype, ir.DataTypeGetIF) else "out",
                             "bits": f.datatype.element_type.bits,
                             "sv_type": f.pragmas.get("sv_type")})
        elif isinstance(f.datatype, ir.DataTypeChannel):
            sh.channels.append({"name": f.name, "bits": f.datatype.element_type.bits,
                                "depth": f.datatype.depth, "sv_type": f.pragmas.get("sv_type")})
    for c in st.children.values():
        sh.children.append({"name": c.name, "class": c.spelling,
                            "module": module_name(c.spelling), "engine": engine})
    for b in comp.bind_map:
        sh.binds.append({"port": list(_path_name(comp, b.lhs)),
                         "provider": list(_path_name(comp, b.rhs))})
    return sh


def partition(files: Sequence[str], top: str, xls: Sequence[str],
              config: Optional[FlowConfig] = None,
              reporter: Optional[ErrorReporter] = None) -> Partition:
    config = config or FlowConfig()
    reporter = reporter or ErrorReporter()
    parser = _parse(files, config, reporter)
    sm = StructureMapper(config, reporter, parser.source_manager)
    st = sm.map_structure(_find_class(parser, top), spelling=top)
    used = {c.spelling for c in st.children.values()}
    unused = [x for x in xls if x not in used]
    if unused:
        raise XlsFlowError(f"{unused} assigned to XLS but not instantiated in {top}; "
                           f"its children are {sorted(used)}")
    blocks: Dict[str, ir.DataTypeComponent] = {}
    for c in st.children.values():
        if c.spelling not in xls:
            raise sm.fail(f"child {c.name!r} ({c.spelling}) is not assigned to an engine; "
                          f"X2 implements children with XLS only, so list it in `xls`",
                          c.decl)
        if c.spelling not in blocks:
            blocks[c.spelling] = StaticMapper(config, reporter, parser.source_manager) \
                .map_component(c.cls, spelling=c.spelling)
    return Partition(st, blocks, _shell(st))


@dc.dataclass
class Block:
    """B's output for one class."""
    signature: ir.BlockSignature
    verilog: str


def xls_block(comp: ir.DataTypeComponent, stages: int = 1,
              opts=None) -> Block:
    """XLS IR -> ``opt_main`` -> ``codegen_main`` for one class."""
    from zuspec.be.xls.lower_proc import lower_component
    from zuspec.be.xls.printer import format_package
    from zuspec.be.xls.signature import CodegenOptions, actual_signature, predict_signature
    from zuspec.be.xls.testing.xlstools import run_codegen
    opts = opts or CodegenOptions(module_name=module_name(comp.name))
    res = run_codegen(format_package(lower_component(comp)), opts, stages=stages)
    sig = actual_signature(predict_signature(comp, opts), res.signature,
                           sources=[f"{opts.module_name}.sv"])
    return Block(sig, res.verilog)


def _path_name(comp: ir.DataTypeComponent, e: ir.Expr) -> Tuple[str, Optional[str]]:
    if isinstance(e, ir.ExprAttribute):
        return comp.fields[e.value.index].name, e.attr
    return comp.fields[e.index].name, None


def integrate(shell: Shell, sigs: Dict[str, ir.BlockSignature],
              top_name: Optional[str] = None, clock: str = "clk",
              reset: str = "rst") -> Tuple[ir.DataTypeComponent, ir.BlockSignature]:
    """The structural top for *shell*, from the blocks' signatures (keyed by
    module name). Returns the top's IR and its own signature."""
    top_name = top_name or shell.module
    u1 = lambda: ir.DataTypeInt(bits=1, signed=False)  # noqa: E731
    fields: List[ir.Field] = [ir.FieldInOut(name=clock, datatype=u1(), is_out=False),
                              ir.FieldInOut(name=reset, datatype=u1(), is_out=False)]
    top_sig = ir.BlockSignature(name=top_name, clock=clock, reset=reset, engine="structural")

    # Own ports -> ready/valid pins (INT-3): <p>, <p>_vld, <p>_rdy.
    # nets[(name, end)] = (data, valid, ready) signal names
    nets: Dict[Tuple[str, Optional[str]], Tuple[str, str, str]] = {}
    for p in shell.ports:
        n, w, inbound = p["name"], p["bits"], p["direction"] == "in"
        fields += [ir.FieldInOut(name=n, datatype=ir.DataTypeInt(bits=w, signed=False),
                                 is_out=not inbound),
                   ir.FieldInOut(name=f"{n}_vld", datatype=u1(), is_out=not inbound),
                   ir.FieldInOut(name=f"{n}_rdy", datatype=u1(), is_out=inbound)]
        nets[(n, None)] = (n, f"{n}_vld", f"{n}_rdy")
        top_sig.channels.append(ir.ChannelSignature(
            name=n, direction=p["direction"], payload=ir.DataTypeInt(bits=w, signed=False),
            ports={"data": n, "valid": f"{n}_vld", "ready": f"{n}_rdy"},
            payload_sv_type=p.get("sv_type")))

    # Channels -> an fw_rv_fifo each, with nets <ch>_in* and <ch>_out*.
    instances: List[ir.ModuleInstance] = []
    for c in shell.channels:
        n, w = c["name"], c["bits"]
        for side in ("in", "out"):
            fields += [ir.Field(name=f"{n}_{side}", datatype=ir.DataTypeInt(bits=w, signed=False)),
                       ir.Field(name=f"{n}_{side}_vld", datatype=u1()),
                       ir.Field(name=f"{n}_{side}_rdy", datatype=u1())]
        nets[(n, "put_ex")] = (f"{n}_in", f"{n}_in_vld", f"{n}_in_rdy")
        nets[(n, "get_ex")] = (f"{n}_out", f"{n}_out_vld", f"{n}_out_rdy")
        instances.append(ir.ModuleInstance(
            module=FIFO_MODULE, name=n, parameters={"WIDTH": str(w), "DEPTH": str(c["depth"])},
            connections=[ir.PortConnection(port=p, signal=s) for p, s in [
                ("clk", clock), ("rst", reset),
                ("in_data", f"{n}_in"), ("in_vld", f"{n}_in_vld"), ("in_rdy", f"{n}_in_rdy"),
                ("out_data", f"{n}_out"), ("out_vld", f"{n}_out_vld"),
                ("out_rdy", f"{n}_out_rdy")]]))

    # Children -> one instance each, wired by the binds.
    provider = {tuple(b["port"]): tuple(b["provider"]) for b in shell.binds}
    for c in shell.children:
        sig = sigs.get(c["module"])
        if sig is None:
            raise XlsFlowError(f"no block signature for {c['name']} (module {c['module']!r})")
        conns = [ir.PortConnection(port=sig.clock, signal=clock)]
        if sig.reset:
            conns.append(ir.PortConnection(port=sig.reset, signal=reset))
        for ch in sig.channels:
            data, vld, rdy = nets[provider[(c["name"], ch.name)]]
            conns += [ir.PortConnection(port=ch.ports["data"], signal=data),
                      ir.PortConnection(port=ch.ports["valid"], signal=vld),
                      ir.PortConnection(port=ch.ports["ready"], signal=rdy)]
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
               reporter: Optional[ErrorReporter] = None) -> RtlDesign:
    """A -> B for each XLS class -> C, in one call."""
    part = partition(files, top, xls, config, reporter)
    sigs: Dict[str, ir.BlockSignature] = {}
    out: Dict[str, str] = {}
    for spelling, comp in part.blocks.items():
        blk = xls_block(comp, stages=stages)
        sigs[blk.signature.name] = blk.signature
        out[blk.signature.sources[0]] = blk.verilog
    top_comp, top_sig = integrate(part.shell, sigs)
    top_sig.sources = [f"{top_sig.name}.sv"]
    out[top_sig.sources[0]] = emit_sv(_b.context([top_comp]))
    return RtlDesign(top_sig.name, out, top_sig, sigs)
