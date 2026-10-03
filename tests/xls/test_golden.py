"""BX-7: the emitted XLS IR for each corpus design, kept as reviewed text.

A change to the emitter shows up here as a diff to read, separately from
whether the results still match (the conformance tests). After reviewing a
change, regenerate with ``XLS_GOLDEN_UPDATE=1``.
"""
import os
from pathlib import Path

import pytest

from fw.hdl.xls_flow import sv_functions_to_xls, sv_to_xls
from zuspec.be.xls.printer import format_package
from zuspec.be.xls.testing.typecheck import check_package

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GOLDEN = HERE / "golden"
UPDATE = os.environ.get("XLS_GOLDEN_UPDATE") == "1"

PROCS = [
    ("crc32_stream", ["corpus/crc32_pkg.sv"]),
    ("rle_enc8_t", ["corpus/rle_pkg.sv", "corpus/rle8_pkg.sv"]),
    ("aes_ctr", ["corpus/aes_pkg.sv"]),
    ("p_acc", ["micro/micro_proc_pkg.sv"]),
    ("p_temp", ["micro/micro_proc_pkg.sv"]),
    ("p_pred", ["micro/micro_proc_pkg.sv"]),
    ("p_frame", ["micro/micro_proc_pkg.sv"]),
]
FUNCTIONS = [
    ("aes128_encrypt", ["corpus/aes_pkg.sv"]),
    ("crc32_4", ["corpus/crc32_pkg.sv"]),
]


def _text(pkg) -> str:
    check_package(pkg)
    # Source paths relative to the repository, so the file is portable.
    return format_package(pkg).replace(str(REPO) + "/", "")


def _compare(name: str, text: str) -> None:
    path = GOLDEN / f"{name}.ir"
    if UPDATE or not path.exists():
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(text)
        if not UPDATE:
            pytest.skip(f"wrote new golden {path.name}; review and commit it")
        return
    assert text == path.read_text(), (
        f"{name}: emitted XLS IR differs from {path}; review the change, then "
        f"rerun with XLS_GOLDEN_UPDATE=1")


@pytest.mark.parametrize("top,files", PROCS, ids=[p[0] for p in PROCS])
def test_golden_proc(top, files):
    _compare(top, _text(sv_to_xls([str(HERE / f) for f in files], top)))


@pytest.mark.parametrize("fn,files", FUNCTIONS, ids=[f[0] for f in FUNCTIONS])
def test_golden_function(fn, files):
    _compare(fn, _text(sv_functions_to_xls([str(HERE / f) for f in files], [fn])))
