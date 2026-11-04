"""The cosim specs in tests/stdlib/cosim/ (fw.hdl.verif.cosim): fw-hdl's own
lowering of each class, and a supplied arbiter, against the class's contract.
Some runs must fail: the supplied arbiter without its grant lock, a credit
sender held to fewer credits than it was built with, FIFOs (in flops and in
a RAM) held to a DEPTH they do not keep, and a table, a token pool and a slot reserve held to less
than they have, and dependency trackers that never wait or never release."""
import dataclasses as dc
from pathlib import Path

import pytest

from fw.hdl.verif import cosim
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main

HERE = Path(__file__).resolve().parent
SPECS = HERE / "cosim"
VERILATOR = HERE.parents[1] / "packages" / "verilator" / "bin" / "verilator"
SEEDS = (1, 2, 3, 4)

pytestmark = [
    pytest.mark.skipif(not VERILATOR.exists(), reason="needs Verilator"),
    pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                       reason="needs opt_main and codegen_main"),
]


def _run(tmp_path, spec, targets=None):
    return cosim.run(spec, tmp_path, SEEDS, targets, str(VERILATOR))


@pytest.mark.parametrize("name", ["fw_arbiter", "fw_credit_tx", "fw_credit_tx_c4",
                                  "fw_channel", "fw_channel_sram", "fw_keyed_table",
                                  "fw_token_pool",
                                  "fw_slot_reserve", "fw_dep_tracker"])
def test_spec_passes(tmp_path, name):
    spec = cosim.load(SPECS / f"{name}.yaml")
    targets = [t.name for t in spec.targets if not (t.name.endswith("_nolock") or t.name.startswith("bad_"))]
    res = _run(tmp_path, spec, targets)
    assert len(res) == len(targets) * len(SEEDS)
    assert {k: v for k, v in res.items() if v} == {}


def test_unlocked_grant_is_caught(tmp_path):
    """Without its lock, the supplied arbiter re-arbitrates while out is
    stalled: a later arrival changes out while it is valid."""
    res = _run(tmp_path, cosim.load(SPECS / "fw_arbiter.yaml"), ["ref_nolock"])
    errs = [e for v in res.values() for e in v]
    assert errs and all("out: valid or data changed" in e for e in errs), errs


def test_overspend_is_caught(tmp_path):
    """The same RTL held to 4 credits: it spends its 6."""
    spec = cosim.load(SPECS / "fw_credit_tx.yaml")
    spec = dc.replace(spec, params=dict(spec.params, CREDITS=4))
    errs = [e for v in _run(tmp_path, spec).values() for e in v]
    assert errs and all("more than CREDITS=4" in e for e in errs), errs


@pytest.mark.parametrize("depth, msg", [(3, "more than DEPTH=2"), (0, "(a bypass)")],
                         ids=["deeper", "wire"])
def test_fifo_held_to_depth_2(tmp_path, depth, msg):
    """fw_rv_fifo built 3 deep holds a third value; built as a wire it
    passes a value in the cycle it came."""
    spec = cosim.load(SPECS / "fw_channel.yaml")
    t = spec.targets[0]
    spec = dc.replace(spec, targets=[dc.replace(t, params=dict(t.params, DEPTH=depth))])
    errs = [e for v in _run(tmp_path, spec).values() for e in v]
    assert errs and all(msg in e for e in errs), errs


def test_sram_fifo_held_to_depth_4(tmp_path):
    """The SRAM FIFO built 5 deep holds a fifth value."""
    spec = cosim.load(SPECS / "fw_channel_sram.yaml")
    t = next(t for t in spec.targets if t.name == "sram")
    spec = dc.replace(spec, targets=[dc.replace(t, params=dict(t.params, DEPTH=5))])
    errs = [e for v in _run(tmp_path, spec).values() for e in v]
    assert errs and all("more than DEPTH=4" in e for e in errs), errs


def test_table_held_to_7_slots(tmp_path):
    """fw_keyed_table built with 8 slots, held to 7: once 7 are live, an
    install that should be refused as full takes the eighth."""
    spec = cosim.load(SPECS / "fw_keyed_table.yaml")
    spec = dc.replace(spec, params=dict(spec.params, N=7))
    errs = [e for v in _run(tmp_path, spec, ["own"]).values() for e in v]
    assert errs and all("no order of the requests gives the responses" in e
                        for e in errs), errs


@pytest.mark.parametrize("name, n, msg", [("fw_token_pool", 3, "granted, but there are N=3"),
                                         ("fw_slot_reserve", 5, "more than N=5")],
                         ids=["pool", "reserve"])
def test_pool_held_to_less(tmp_path, name, n, msg):
    """A token pool built with 4 tokens, held to 3, grants the fourth; a
    slot reserve built with 6 slots, held to 5, reserves the sixth."""
    spec = cosim.load(SPECS / f"{name}.yaml")
    spec = dc.replace(spec, params=dict(spec.params, N=n))
    errs = [e for v in _run(tmp_path, spec, ["own"]).values() for e in v]
    assert errs and all(msg in e for e in errs), errs


@pytest.mark.parametrize("target, msg", [("bad_nowait", "has not retired"),
                                         ("bad_noreleases", "still waiting")])
def test_dep_tracker_faults_are_caught(tmp_path, target, msg):
    spec = cosim.load(SPECS / "fw_dep_tracker.yaml")
    errs = [e for v in _run(tmp_path, spec, [target]).values() for e in v]
    assert errs and all(msg in e for e in errs), errs


def test_unmapped_port_is_named():
    spec = cosim.load(SPECS / "fw_arbiter.yaml")
    t = dc.replace(spec.targets[2], ports={k: v for k, v in spec.targets[2].ports.items()
                                           if k != "in[1]"})
    drv = cosim.DRIVERS[spec.cls](spec.params)
    with pytest.raises(ValueError, match=r"port in\[1\] is not mapped"):
        cosim.testbench(t, drv.ports(), {}, 1)
