"""Native children: blocks fw-hdl emits itself, without XLS (RQ-F2 ``native``).

The one native kind so far is a register block as a child, an
``fw_reg_component #(BLK, W, AW)`` (``src/std/fw_reg_component.svh``):

* its ``wr`` port, a stream of ``{addr, data}`` software writes, drives the
  core's bus (``s_wr`` on valid; ready is always 1);
* each other port is a level named as a register of ``BLK`` and carries that
  register's value: the core's ``hwif_out`` nets for its fields, with a
  reserved field held at its reset value, as the class model's ``read()``.

A field hardware writes is not supported yet: a register-block child has no
inputs but ``wr``.
"""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Tuple

import zuspec.ir.core as ir

from .emit.regblock import emit_regblock, regblock_ports
from .regmap import RegBlock, Register, RegField

#: The library class a register-block child derives from.
REG_COMPONENT = "fw_reg_component"


class NativeError(Exception):
    pass


def _base_params(cls) -> Tuple[object, int, int]:
    """(BLK class, W, AW) of the fw_reg_component specialization *cls* extends."""
    from pyslang import ast
    from .fe.elab.values import const_to_py
    ct = cls
    while ct is not None:
        g = getattr(ct, "genericClass", None)
        if g is not None and g.name == REG_COMPONENT:
            blk = w = aw = None
            for x in ct:
                if x.kind == ast.SymbolKind.TypeParameter and x.name == "BLK":
                    blk = x.targetType.type.canonicalType
                elif x.kind == ast.SymbolKind.Parameter and x.name == "W":
                    w = int(const_to_py(x.value))
                elif x.kind == ast.SymbolKind.Parameter and x.name == "AW":
                    aw = int(const_to_py(x.value))
            return blk, w, aw
        b = ct.baseClass
        ct = b.canonicalType if b is not None else None
    raise NativeError(f"{cls} does not extend {REG_COMPONENT}")


@dc.dataclass
class RegChild:
    """What a register-block child needs to become RTL."""
    spelling: str
    module: str
    block: RegBlock
    width: int                          # W: the bus data width
    addr_width: int                     # AW
    #: level port -> (qualified register name, register, bits)
    levels: Dict[str, Tuple[str, Register, int]]

    def to_json(self) -> dict:
        return {"kind": "regblock", "block": self.block.name, "W": self.width,
                "AW": self.addr_width,
                "levels": {p: q for p, (q, _r, _b) in sorted(self.levels.items())}}


def _field(o, name):
    from .fe.elab.hier import _prop
    return o.fields.get(_prop(o.cls, name))


def _register(r) -> Register:
    """A register object (an ``fw_reg #(T, W)``, as the interpreter built it)."""
    from pyslang import ast
    from .fe.reg_mapper import RegMapper
    T, W = None, None
    for x in r.cls:
        if x.kind == ast.SymbolKind.TypeParameter and x.name == "T":
            T = x.targetType.type
        elif x.kind == ast.SymbolKind.Parameter and x.name == "W":
            from .fe.elab.values import const_to_py
            W = int(const_to_py(x.value))
    reg = Register(name=_field(r, "m_name"), offset=_field(r, "m_offset"), width=W)
    reg.reset = _field(r, "m_reset")
    reg.sw_wmask = _field(r, "m_sw_wmask")
    reg.hw_wmask = _field(r, "m_hw_wmask")
    reg.rclr_mask = _field(r, "m_rclr_mask")
    for name, lsb, width in RegMapper._struct_fields(None, T, W):
        m = ((1 << width) - 1) << lsb
        reg.fields.append(RegField(name=name, lsb=lsb, width=width,
                                   sw_write=bool(reg.sw_wmask & m),
                                   hw_write=bool(reg.hw_wmask & m),
                                   rclr=bool(reg.rclr_mask & m),
                                   reset=(reg.reset >> lsb) & ((1 << width) - 1)))
    return reg


def _block(b, regs: Dict[int, Register]) -> RegBlock:
    """A register-block object -> RegBlock; *regs* collects oid -> Register."""
    blk = RegBlock(name=b.cls.name)
    seen = {}
    for d in (_field(b, "m_rd_regs") or {}, _field(b, "m_wr_regs") or {}):
        for r in d.values():
            seen.setdefault(r.oid, r)
    for r in sorted(seen.values(), key=lambda r: _field(r, "m_offset")):
        regs[r.oid] = _register(r)
        blk.registers.append(regs[r.oid])
    for off, sub in sorted((_field(b, "m_blocks") or {}).items()):
        blk.subblocks.append((off, _block(sub, regs)))
    blk.size = _field(b, "m_size")
    return blk


def reg_child(child, module: str) -> RegChild:
    """*child* is a ``fe.structure.Child`` whose class extends fw_reg_component.
    The register block and which register each level port carries are read
    from the elaborated objects (``drive`` calls in ``connect()``)."""
    _blk_cls, w, aw = _base_params(child.cls)
    o = child.node.obj
    regs: Dict[int, Register] = {}
    blk = _block(_field(o, "blk"), regs)
    qual = {id(r): q for _o, q, r in blk.flat_registers()}
    driven: Dict[int, Tuple[str, Register]] = {}    # port oid -> (qreg, register)
    for lv in _field(o, "m_levels") or []:
        r, p = _field(lv, "m_r"), _field(lv, "m_p")
        reg = regs.get(getattr(r, "oid", None))
        if reg is None:
            raise NativeError(f"{child.name}: drive() of a register that is not in blk")
        if p.oid in driven:
            raise NativeError(f"{child.name}.{_field(p, 'm_ep_name')}: driven twice")
        driven[p.oid] = (qual[id(reg)], reg)
    levels: Dict[str, Tuple[str, Register, int]] = {}
    for pname, port in child.node.ports.items():
        if pname == "wr":
            continue
        f = child.ports[pname]
        if f.pragmas.get("fw_flow") != "level" or isinstance(f.datatype, ir.DataTypeGetIF):
            raise NativeError(f"{child.name}.{pname}: a register-block child's ports are `wr` "
                              f"and level outputs (fw_level_set_if)")
        if port.obj.oid not in driven:
            raise NativeError(f"{child.name}.{pname}: no register drives it; add "
                              f"drive(fw_reg_level #(T)::make(blk.<reg>, {pname})) to connect()")
        q, reg = driven[port.obj.oid]
        bits = f.datatype.element_type.bits
        hw = [fl.name for fl in reg.fields if fl.hw_write]
        if hw:
            raise NativeError(f"{child.name}.{pname}: fields {hw} of register {q} are written "
                              f"by hardware, which a register-block child does not support yet")
        levels[pname] = (q, reg, bits)
    wr = child.ports.get("wr")
    if wr is None or wr.datatype.element_type.bits != aw + w:
        raise NativeError(f"{child.name}: no `wr` port of {aw + w} bits")
    return RegChild(child.spelling, module, blk, w, aw, levels)


def _u(bits: int) -> ir.DataTypeInt:
    return ir.DataTypeInt(bits=bits, signed=False)


def reg_child_rtl(rc: RegChild) -> Tuple[ir.BlockSignature, str]:
    """The wrapper and core module text, and the wrapper's signature."""
    core = f"{rc.module}_core"
    ports = {p.name: p for p in regblock_ports(rc.block)}
    core_aw = ports["s_addr"].width
    W, AW = rc.width, rc.addr_width
    L = [f"// Register-block child {rc.spelling} (block {rc.block.name}): software writes",
         "// in on `wr` ({addr, data}), registers out as levels.",
         "/* verilator lint_off UNUSEDSIGNAL */",
         f"module {rc.module} (",
         "  input  logic clk,", "  input  logic rst,",
         f"  input  logic [{AW + W - 1}:0] wr,", "  input  logic wr_vld,",
         "  output logic wr_rdy" + ("," if rc.levels else "")]
    names = sorted(rc.levels)
    L += [f"  output logic [{rc.levels[n][2] - 1}:0] {n}" + ("," if i + 1 < len(names) else "")
          for i, n in enumerate(names)]
    L += [");", "  assign wr_rdy = 1'b1;", f"  logic [{W - 1}:0] rdata;   // no read path"]
    conns = [".clock(clk)", ".reset(rst)", f".s_addr(wr[{W + core_aw - 1}:{W}])",
             ".s_wr(wr_vld)", f".s_wdata(wr[{W - 1}:0])", ".s_rd(1'b0)", ".s_rdata(rdata)"]
    for _o, q, reg in rc.block.flat_registers():
        for f in reg.fields:
            pin = f"hwif_out_{q}__{f.name}"
            if pin in ports:
                L.append(f"  logic [{f.width - 1}:0] {pin};")
                conns.append(f".{pin}({pin})")
    for n in names:
        q, reg, bits = rc.levels[n]
        L.append(f"  always_comb begin")
        L.append(f"    {n} = '0;")
        for f in reg.fields:
            if f.lsb >= bits:
                continue
            pin = f"hwif_out_{q}__{f.name}"
            src = pin if pin in ports else f"{f.width}'h{f.reset:x}"
            L.append(f"    {n}[{f.msb}:{f.lsb}] = {src};")
        L.append("  end")
    L += [f"  {core} u_core(" + ", ".join(conns) + ");", "endmodule",
          "/* verilator lint_on UNUSEDSIGNAL */", ""]
    # the core and the wrapper share one file
    text = "/* verilator lint_off DECLFILENAME */\n" + emit_regblock(rc.block, module_name=core) \
        + "\n" + "\n".join(L)
    sig = ir.BlockSignature(name=rc.module, clock="clk", reset="rst", engine="native",
                            sources=[f"{rc.module}.sv"])
    sig.channels.append(ir.ChannelSignature(
        name="wr", direction="in", payload=_u(AW + W), flow_control="ready_valid",
        ports={"data": "wr", "valid": "wr_vld", "ready": "wr_rdy"}))
    for n in names:
        sig.channels.append(ir.ChannelSignature(
            name=n, direction="out", payload=_u(rc.levels[n][2]), flow_control="none",
            ports={"data": n}))
    return sig, text
