"""The structured ``regblock_ports()`` must agree with the regblock the text
emitter produces — they are two views of the same module header and structural
assembly relies on them matching (the guard against divergence)."""
import re

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.reg_mapper import build_reg_blocks
from fw.hdl.fe.reg_consumer import analyze_consumer
from fw.hdl.emit.regblock import emit_regblock, regblock_ports


def _emitted_ports(sv: str):
    """Parse (direction, name) for each port in the emitted module header."""
    header = sv.split("module", 1)[1].split("(", 1)[1].split(");", 1)[0]
    out = []
    for line in header.splitlines():
        m = re.match(r"\s*(input|output)\s+logic\s*(\[[^\]]*\])?\s*(\w+)\s*,?\s*$", line)
        if m:
            out.append(("in" if m.group(1) == "input" else "out", m.group(3)))
    return out


def test_regblock_ports_match_emitted_header(mmio_files):
    rep = ErrorReporter()
    blk = build_reg_blocks(mmio_files, FlowConfig(), rep)["mmio_regs"]
    usage = analyze_consumer(mmio_files, "mmio_fsm", FlowConfig(), rep)
    assert not rep.has_errors(), rep.report()

    structured = [(p.direction, p.name) for p in regblock_ports(blk, usage)]
    emitted = _emitted_ports(emit_regblock(blk, usage=usage))
    assert structured == emitted


def test_regblock_ports_match_dma_channel(reg_dma_files):
    """A richer block (providers/observers/rclr via the DMA map) also agrees."""
    rep = ErrorReporter()
    blk = build_reg_blocks(reg_dma_files, FlowConfig(), rep)["dma_regs"]
    usage = analyze_consumer(reg_dma_files, "dma_engine", FlowConfig(), rep)
    assert not rep.has_errors(), rep.report()

    structured = [(p.direction, p.name) for p in regblock_ports(blk, usage)]
    emitted = _emitted_ports(emit_regblock(blk, usage=usage))
    assert structured == emitted
