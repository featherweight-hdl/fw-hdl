import os
import sys
from pathlib import Path

import pytest

_here = Path(__file__).resolve().parent
for p in (_here, _here.parents[1] / "python"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def pytest_collection_modifyitems(config, items):
    from xls_harness import have_verilator
    if not os.environ.get("FW_HDL_RUN_BIGMEM"):
        skip_big = pytest.mark.skip(reason="needs tens of GB of memory; "
                                    "set FW_HDL_RUN_BIGMEM=1 to run it")
        for item in items:
            if item.get_closest_marker("bigmem") is not None:
                item.add_marker(skip_big)
    if have_verilator():
        return
    skip = pytest.mark.skip(reason="verilator not found (FW_HDL_VERILATOR, packages/verilator, PATH)")
    for item in items:
        if item.get_closest_marker("verilator") is not None:
            item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "verilator: runs the SV on Verilator")
    config.addinivalue_line(
        "markers", "bigmem: needs far more memory than a CI runner has; skipped "
                   "unless FW_HDL_RUN_BIGMEM is set")


@pytest.fixture
def workdir(tmp_path):
    return tmp_path
