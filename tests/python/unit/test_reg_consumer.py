"""M7: consumer-usage recognition — recover a hardware component's register usage
(watch-set memberships, providers, observers) and resolve each register reference
to an absolute offset, generically (loop-unrolled, no field-name matching)."""
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.reg_consumer import analyze_consumer


def _usage(reg_dma_files, comp):
    rep = ErrorReporter()
    u = analyze_consumer(reg_dma_files, comp, FlowConfig(), rep)
    assert u is not None and not rep.has_errors(), rep.report()
    return u


def test_engine_watch_set_members(reg_dma_files):
    """The engine adds every channel's CSR to one watch-set via a for-loop; the
    members resolve to the 31 channel-CSR offsets 0x20, 0x40, ... 0x3e0."""
    u = _usage(reg_dma_files, "dma_engine")
    assert list(u.change_sets.keys()) == ["m_csrs"]
    members = u.change_sets["m_csrs"]
    assert len(members) == 31
    assert members == [0x20 + i * 0x20 for i in range(31)]
    assert members[0] == 0x20 and members[-1] == 0x3E0


def test_engine_has_no_providers_or_observers(reg_dma_files):
    u = _usage(reg_dma_files, "dma_engine")
    assert u.providers == [] and u.observers == []


def test_consumer_without_block_is_empty(reg_dma_files):
    """A component that holds no register block yields empty usage (host talks to
    the device over the bus, not via register handles)."""
    u = _usage(reg_dma_files, "dma_host")
    assert u.change_sets == {} and u.observers == [] and u.providers == []
