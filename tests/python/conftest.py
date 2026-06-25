"""Shared pytest fixtures for the fw-hdl Python tests.

Adds ``python/`` to ``sys.path`` so ``import fw.hdl`` works without an install,
and exposes repo paths.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PY_DIR = REPO_ROOT / "python"
UNIT_DIR = Path(__file__).parent / "unit"   # holds shared fixtures + @zdc models
for d in (PY_DIR, UNIT_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

BLINKY_DIR = REPO_ROOT / "tests" / "blinky"


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def blinky_dir() -> Path:
    return BLINKY_DIR


@pytest.fixture
def blinky_files():
    return [str(BLINKY_DIR / f) for f in ("blinky_pkg.sv", "blinky_top.sv")]


REG_DMA_DIR = REPO_ROOT / "tests" / "reg_dma"


@pytest.fixture
def reg_dma_files():
    # the tb is included so the auto-included fw_root module binds a concrete
    # Tbind (dma_top) and elaborates cleanly, as for blinky_files.
    return [str(REG_DMA_DIR / f) for f in ("reg_dma_pkg.sv", "reg_dma_tb.sv")]


MMIO_DIR = REPO_ROOT / "tests" / "mmio"


@pytest.fixture
def mmio_dir() -> Path:
    return MMIO_DIR


@pytest.fixture
def mmio_files():
    # the class-level tb seats fw_root so the package elaborates during sv2ir.
    return [str(MMIO_DIR / f) for f in ("mmio_pkg.sv", "mmio_tb.sv")]
