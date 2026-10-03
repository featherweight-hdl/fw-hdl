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
    if have_verilator():
        return
    skip = pytest.mark.skip(reason="verilator not found in packages/verilator")
    for item in items:
        if item.get_closest_marker("verilator") is not None:
            item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "verilator: runs the SV on Verilator")


@pytest.fixture
def workdir(tmp_path):
    return tmp_path
