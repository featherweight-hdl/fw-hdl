"""The cosim specs in tests/stdlib/cosim/ (fw.hdl.verif.cosim): fw-hdl's own
lowering of each class, and a supplied arbiter, against the class's contract.
Two runs must fail: the supplied arbiter without its grant lock, and a
credit sender held to fewer credits than it was built with."""
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


@pytest.mark.parametrize("name", ["fw_arbiter", "fw_credit_tx", "fw_credit_tx_c4"])
def test_spec_passes(tmp_path, name):
    spec = cosim.load(SPECS / f"{name}.yaml")
    targets = [t.name for t in spec.targets if not t.name.endswith("_nolock")]
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


def test_unmapped_port_is_named():
    spec = cosim.load(SPECS / "fw_arbiter.yaml")
    t = dc.replace(spec.targets[2], ports={k: v for k, v in spec.targets[2].ports.items()
                                           if k != "in[1]"})
    drv = cosim.DRIVERS[spec.cls](spec.params)
    with pytest.raises(ValueError, match=r"port in\[1\] is not mapped"):
        cosim.testbench(t, drv.ports(), {}, 1)
