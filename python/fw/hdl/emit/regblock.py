"""Emit a synthesizable SystemVerilog regblock *core* from a ``RegBlock``.

This is the M6 step of the register-model plan (register-model-rtl-lowering.md
§§2-6): the elaborated RegMap becomes one RTL region — storage, address decode,
read mux, and the software write / hardware-update logic.

GENERICITY CONTRACT (deliberate): nothing here keys off user-chosen *names*. A
field's hardware is decided **only** by its mask signature and structural facts
recovered in M5:
  - reserved   (sw=- hw=-)            -> no storage, reads as 0
  - hw-writable                       -> a hardware next/we port drives it
  - sw-writable                       -> a software write-enable drives it
  - sw+hw overlap                     -> hardware wins (priority mux)
  - read-to-clear (rclr)              -> cleared on an accepted software read
Decode style (bit-slice vs. compare) is chosen from the *offsets*, not names.

Storage-elimination optimizations that need consumer information (RO-reflect ->
wire via a read provider; working register -> datapath flop; WO -> strobe) are NOT
done here — they are layered on at M7 once provider/observer/usage is captured.
M6 emits the correct, fully-flopped core; M7 prunes it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..regmap import RegBlock, Register, RegField, RegUsage


@dataclass
class RegPort:
    """One port of a generated regblock module (name, direction, bit-width).

    The structured view of the module header (the formatted text the emitter
    produces and this list must agree, guarded by a test) — so structural
    assembly (emit/structural.py) can wire every port without re-deriving names."""
    name: str
    direction: str       # "in" | "out"
    width: int


def regblock_ports(blk: RegBlock, usage: RegUsage = None) -> List[RegPort]:
    """The regblock module's full port list, mask-driven exactly like
    :func:`emit_regblock` (shared reflect/drop helpers)."""
    regs = blk.flat_registers()
    regs.sort(key=lambda t: t[0])
    if not regs:
        raise ValueError(f"register block {blk.name!r} has no registers")
    W = regs[0][2].width
    AW = max(_clog2(blk.size), 1)
    prov = set(usage.providers) if usage else set()

    out = [RegPort("clock", "in", 1), RegPort("reset", "in", 1),
           RegPort("s_addr", "in", AW), RegPort("s_wr", "in", 1),
           RegPort("s_wdata", "in", W), RegPort("s_rd", "in", 1),
           RegPort("s_rdata", "out", W)]
    for (off, qreg, reg) in regs:
        reflect = _reg_reflects(reg, off in prov)
        if reflect:
            out.append(RegPort(f"hwif_in_{qreg}_rdata", "in", W))
        for f in reg.fields:
            if not f.sw_write and not f.hw_write:
                continue                                   # reserved
            if reflect and f.hw_write and not f.sw_write:
                continue                                   # dropped (provider supplies)
            s = _sig(qreg, f.name)
            if f.hw_write:
                out.append(RegPort(f"hwif_in_{s}_next", "in", f.width))
                out.append(RegPort(f"hwif_in_{s}_we", "in", 1))
            out.append(RegPort(f"hwif_out_{s}", "out", f.width))
    for set_name in (usage.change_sets if usage else {}):
        out.append(RegPort(f"{_safe(set_name)}_changed", "out", 1))
    if usage:
        qreg_of = {off: q for (off, q, _r) in regs}
        for off in usage.observers:
            if off in qreg_of:
                out.append(RegPort(f"{qreg_of[off]}__sw_wstrobe", "out", 1))
    return out


def _clog2(n: int) -> int:
    n = max(int(n), 1)
    b = 0
    while (1 << b) < n:
        b += 1
    return b


def _sig(qreg: str, field: str) -> str:
    return f"{qreg}__{field}"


class _Decode:
    """How the register select is computed from the bus address."""
    def __init__(self, regs: List[Tuple[int, str, Register]], W: int):
        self.stride = W // 8
        self.lsb_bits = _clog2(self.stride)
        offs = [o for (o, _, _) in regs]
        n = len(regs)
        # aligned contiguous bank: offsets are 0, stride, 2*stride, ... (no gaps)?
        self.aligned = (n > 0
                        and (self.stride & (self.stride - 1)) == 0
                        and offs == [k * self.stride for k in range(n)])
        self.idx_bits = max(_clog2(n), 1)

    def sel_expr(self, k: int, offset: int) -> str:
        if self.aligned:
            return f"(reg_sel == {self.idx_bits}'d{k})"
        return f"(s_addr == {offset})"   # comparator fallback (non-aligned map)


def _safe(name: str) -> str:
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in name)


def emit_regblock(blk: RegBlock, *, module_name: str = None,
                  usage: RegUsage = None, formal: bool = False) -> str:
    name = module_name or f"{blk.name}_regblock"
    regs = blk.flat_registers()
    regs.sort(key=lambda t: t[0])
    if not regs:
        raise ValueError(f"register block {blk.name!r} has no registers")

    W = regs[0][2].width
    AW = max(_clog2(blk.size), 1)
    dec = _Decode(regs, W)

    # offset -> (qualified-name, Register, select-expression) for usage emission
    meta = {}
    for (off, qreg, reg) in regs:
        k = off // dec.stride if dec.aligned else off
        meta[off] = (qreg, reg, dec.sel_expr(k, off))

    # A register with a read provider is reflected: its readback is supplied live
    # by the provider (fw_reg_rd_if.on_read is register-level and is the single
    # source of truth when attached), so its hw-only fields need no storage.
    # rclr + a provider are mutually exclusive (register-model-design.md §3), so a
    # register with any read-clear field is NOT reflected (and is noted).
    prov = set(usage.providers) if usage else set()
    notes: List[str] = []

    def reg_reflects(off: int, reg: Register) -> bool:
        if off not in prov:
            return False
        if any(f.rclr for f in reg.fields):
            return False
        return any(f.hw_write and not f.sw_write for f in reg.fields)

    def dropped(off: int, reg: Register, f: RegField) -> bool:
        # a hw-only field of a reflected register: provider supplies it, no storage
        return reg_reflects(off, reg) and f.hw_write and not f.sw_write

    for (off, qreg, reg) in regs:
        if off in prov and not reg_reflects(off, reg) and any(f.rclr for f in reg.fields):
            notes.append(f"// note: '{qreg}' has a read provider but read-clear "
                         f"fields; not reflected (rclr + provider are exclusive).")

    L: List[str] = []
    ap = L.append

    # ---- module header + ports ------------------------------------------
    ports: List[str] = [
        "input  logic            clock",
        "input  logic            reset",
        f"input  logic [{AW-1}:0] {'s_addr':>7}",
        f"input  logic            s_wr",
        f"input  logic [{W-1}:0] s_wdata",
        f"input  logic            s_rd",
        f"output logic [{W-1}:0] s_rdata",
    ]
    # hwif ports, per field, driven purely by the mask signature (+ provider)
    for (off, qreg, reg) in regs:
        if reg_reflects(off, reg):
            # whole-register readback supplied by the provider's on_read output
            ports.append(f"input  logic [{W-1}:0] hwif_in_{qreg}_rdata")
        for f in reg.fields:
            if not f.sw_write and not f.hw_write:
                continue                                   # reserved: no hwif
            if dropped(off, reg, f):
                continue                                   # provider supplies; no port
            s = _sig(qreg, f.name)
            if f.hw_write:
                ports.append(f"input  logic [{f.width-1}:0] hwif_in_{s}_next")
                ports.append(f"input  logic            hwif_in_{s}_we")
            ports.append(f"output logic [{f.width-1}:0] hwif_out_{s}")

    # consumer-facing outputs (watch-set change pulses, observer write strobes)
    for set_name in (usage.change_sets if usage else {}):
        ports.append(f"output logic            {_safe(set_name)}_changed")
    for off in (usage.observers if usage else []):
        if off in meta:
            ports.append(f"output logic            {meta[off][0]}__sw_wstrobe")

    ap(f"// Generated regblock core for '{blk.name}' (W={W}, size=0x{blk.size:x}).")
    ap(f"// Decode: {'bit-slice (aligned bank)' if dec.aligned else 'address compare'}.")
    for n in notes:
        ap(n)
    # word-level access leaves the low byte-offset bits of s_addr unused by design
    ap("/* verilator lint_off UNUSEDSIGNAL */")
    ap(f"module {name} (")
    ap(",\n".join("  " + p for p in ports))
    ap(");")
    ap("")

    # ---- register-select slice ------------------------------------------
    if dec.aligned:
        hi = dec.lsb_bits + dec.idx_bits - 1
        ap(f"  logic [{dec.idx_bits-1}:0] reg_sel;")
        ap(f"  assign reg_sel = s_addr[{hi}:{dec.lsb_bits}];   // no address comparator")
        ap("")

    # ---- storage + per-field update logic -------------------------------
    for (off, qreg, reg) in regs:
        k = off // dec.stride if dec.aligned else off
        sel = dec.sel_expr(k, off)
        for f in reg.fields:
            if not f.sw_write and not f.hw_write:
                continue                                   # reserved: constant 0
            if dropped(off, reg, f):
                continue                                   # provider supplies; no storage
            s = _sig(qreg, f.name)
            ap(f"  logic [{f.width-1}:0] field_{s};")
            ap(f"  assign hwif_out_{s} = field_{s};")
            ap(f"  always_ff @(posedge clock) begin")
            ap(f"    if (reset) field_{s} <= {f.width}'h{f.reset:x};")
            terms: List[str] = []
            if f.hw_write:
                terms.append((f"hwif_in_{s}_we", f"hwif_in_{s}_next"))
            if f.sw_write:
                hi = f.lsb + f.width - 1
                terms.append((f"({sel} && s_wr)", f"s_wdata[{hi}:{f.lsb}]"))
            if f.rclr:
                terms.append((f"({sel} && s_rd)", f"{f.width}'h0"))
            first = True
            for (cond, val) in terms:
                kw = "else if" if not first else "else if"
                ap(f"    {kw} ({cond}) field_{s} <= {val};")
                first = False
            ap(f"  end")
            ap("")

    # ---- read mux --------------------------------------------------------
    ap("  always_comb begin")
    ap("    s_rdata = '0;")
    indent = "    "
    if dec.aligned:
        ap("    unique case (reg_sel)")
        for (off, qreg, reg) in regs:
            k = off // dec.stride
            ap(f"      {dec.idx_bits}'d{k}: begin")
            _emit_read_word(ap, off, qreg, reg, "        ", reg_reflects)
            ap("      end")
        ap("      default: s_rdata = '0;")
        ap("    endcase")
    else:
        for i, (off, qreg, reg) in enumerate(regs):
            kw = "if" if i == 0 else "else if"
            ap(f"    {kw} (s_addr == {off}) begin")
            _emit_read_word(ap, off, qreg, reg, "      ", reg_reflects)
            ap("    end")
    ap("  end")
    ap("")

    # ---- consumer-facing strobes (wait_change sets, on_write observers) --
    if usage and (usage.change_sets or usage.observers):
        ap("  // wake on SOFTWARE writes to members. The consumer that waits on a")
        ap("  // set also drives those registers' hardware side, so including its")
        ap("  // own hw updates would only self-wake (register-model-rtl-lowering")
        ap("  // §9.4 self-wake elimination); the sw write is the real event.")
        for set_name, members in usage.change_sets.items():
            terms = [f"({meta[off][2]} && s_wr)" for off in members if off in meta]
            rhs = " || ".join(terms) if terms else "1'b0"
            ap(f"  assign {_safe(set_name)}_changed = {rhs};")
        for off in usage.observers:
            if off in meta:
                qreg, _reg, sel = meta[off]
                ap(f"  assign {qreg}__sw_wstrobe = ({sel} && s_wr);")
        ap("")

    # ---- formal contract assertions (mask-driven, generic) --------------
    if formal:
        _emit_formal(ap, regs, meta, reg_reflects, dropped)

    ap("  /* verilator lint_on UNUSEDSIGNAL */")
    ap("endmodule")
    return "\n".join(L) + "\n"


def _emit_formal(ap, regs, meta, reg_reflects, dropped) -> None:
    """Embed the register contract as SVA, proven by SymbiYosys. Each property is
    derived from a field's mask profile alone (no names):
      - config (sw-only)   : changes only on a software write to its register
      - RO (hw-only)       : changes only on a hardware write  (RO immutability)
      - sticky (hw + rclr) : changes only on a hw write or an accepted read, and an
                             accepted read with no concurrent hw write clears it
      - overlap (sw + hw)  : changes only on a hw or sw write
      - any hw-writable     : a hardware write wins  (value == hw next-value)
    The per-register select gating also proves decode has no aliasing.
    """
    ap("`ifdef FORMAL")
    for (off, qreg, reg) in regs:
        ap(f"  logic {qreg}__fv_sel; assign {qreg}__fv_sel = {meta[off][2]};")
    ap("  logic fv_past_valid = 1'b0;")
    ap("  always @(posedge clock) fv_past_valid <= 1'b1;")
    ap("  always @(*) if (!fv_past_valid) assume (reset);")
    ap("  always @(posedge clock) if (fv_past_valid && !$past(reset)) begin")
    for (off, qreg, reg) in regs:
        sel = f"{qreg}__fv_sel"
        for f in reg.fields:
            if not f.sw_write and not f.hw_write:
                continue
            if dropped(off, reg, f):
                continue
            s = _sig(qreg, f.name)
            ch = f"(field_{s} != $past(field_{s}))"
            if f.hw_write:                                  # hardware write wins
                ap(f"    if ($past(hwif_in_{s}_we)) "
                   f"assert (field_{s} == $past(hwif_in_{s}_next));")
            if f.rclr:                                      # sticky / read-clear
                ap(f"    if ({ch}) assert ($past(hwif_in_{s}_we) || "
                   f"$past({sel} && s_rd));")
                ap(f"    if ($past({sel} && s_rd) && !$past(hwif_in_{s}_we)) "
                   f"assert (field_{s} == '0);")
            elif f.hw_write and not f.sw_write:             # RO immutability
                ap(f"    if ({ch}) assert ($past(hwif_in_{s}_we));")
            elif f.sw_write and not f.hw_write:             # config
                ap(f"    if ({ch}) assert ($past({sel} && s_wr));")
            else:                                           # sw + hw overlap
                ap(f"    if ({ch}) assert ($past(hwif_in_{s}_we) || "
                   f"$past({sel} && s_wr));")
    ap("  end")
    ap("`endif")


def _reg_reflects(reg: Register, has_provider: bool) -> bool:
    """A register is reflected when it has a read provider, no read-clear field
    (rclr + provider are mutually exclusive, register-model-design.md §3), and at
    least one hw-only field to eliminate. Its whole readback is the provider's
    on_read output (register-model-design.md §1.1: the provider is the single
    source of truth when attached)."""
    return (has_provider
            and not any(f.rclr for f in reg.fields)
            and any(f.hw_write and not f.sw_write for f in reg.fields))


def _emit_read_word(ap, off: int, qreg: str, reg: Register, indent: str,
                    reg_reflects) -> None:
    """A reflected register's readback is the whole provider word; otherwise the
    word is assembled from field storage (reserved bits read 0)."""
    if reg_reflects(off, reg):
        ap(f"{indent}s_rdata = hwif_in_{qreg}_rdata;")
        return
    ap(f"{indent}s_rdata = '0;")
    for f in reg.fields:
        if not f.sw_write and not f.hw_write:
            continue
        s = _sig(qreg, f.name)
        hi = f.lsb + f.width - 1
        ap(f"{indent}s_rdata[{hi}:{f.lsb}] = field_{s};")


# ---- generic field-profile classification (mask-driven, for analysis/tests) --
def classify(f: RegField, has_provider: bool = False) -> str:
    """Storage profile from the mask signature alone (no names, no usage).

    ``has_provider`` is an M7 input (a read provider turns an RO field into a
    wire); at M6 it is always False, so RO fields are 'ro_latched'."""
    if not f.sw_write and not f.hw_write:
        return "reserved"            # 0 flops, constant
    if f.rclr:
        return "sticky"              # set-dominant + read-clear flop
    if f.hw_write and not f.sw_write:
        return "ro_reflect" if has_provider else "ro_latched"
    return "config"                  # sw-writable (covers WO at value level)


def flop_bits(blk: RegBlock, providers=None) -> int:
    """Total storage bits the core allocates: reserved fields cost nothing, and in
    a reflected (provider) register the hw-only fields cost nothing because the
    provider supplies them live."""
    prov = set(providers or [])
    total = 0
    for (off, _q, reg) in blk.flat_registers():
        refl = _reg_reflects(reg, off in prov)
        for f in reg.fields:
            if not (f.sw_write or f.hw_write):
                continue
            if refl and f.hw_write and not f.sw_write:
                continue
            total += f.width
    return total
