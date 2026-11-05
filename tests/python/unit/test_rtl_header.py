"""Module headers read with parameter values applied (fw.hdl.rtl_header)."""
from pathlib import Path

import pytest

from fw.hdl.rtl_header import HeaderError, read_header

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent / "rtl_header"
FIFO = ROOT / "src" / "rtl" / "fw_rv_fifo.sv"
ARB = ROOT / "tests" / "stdlib" / "cosim" / "ref_arb3.sv"


def widths(h):
    return {p.name: (p.direction, p.width) for p in h.ports}


def test_defaults():
    h = read_header([FIFO], "fw_rv_fifo")
    assert h.params == {"WIDTH": 8, "DEPTH": 1}
    assert widths(h)["in_data"] == ("in", 8)
    assert widths(h)["in_rdy"] == ("out", 1)
    assert [p.name for p in h.ports] == ["clk", "rst", "in_data", "in_vld", "in_rdy",
                                        "out_data", "out_vld", "out_rdy"]


def test_overrides_resolve_widths():
    h = read_header([FIFO], "fw_rv_fifo", {"WIDTH": 37, "DEPTH": 4})
    assert h.params == {"WIDTH": 37, "DEPTH": 4}
    assert widths(h)["out_data"] == ("out", 37)


def test_grouped_ansi_declarations():
    h = read_header([ARB], "ref_arb3", {"LOCK": 0})
    w = widths(h)
    assert w["req1_data"] == ("in", 8) and w["req2_ready"] == ("out", 1)
    assert w["gnt_data"] == ("out", 10)
    assert h.params == {"LOCK": 0}


def test_non_ansi_with_localparam_and_string():
    h = read_header([HERE / "nonansi.sv"], "nonansi", {"W": 6, "MODE": "slow"})
    assert h.params == {"W": 6, "MODE": "slow"}
    assert h.localparams == {"W2": 12}
    assert widths(h) == {"clk": ("in", 1), "rst_n": ("in", 1), "a": ("in", 6),
                         "b": ("in", 6), "y": ("out", 12)}


def test_type_parameter_signed_packed_and_define():
    h = read_header([HERE / "typed.sv"], "typed", {"N": 3})
    assert h.type_params == ["T"]
    assert h.port("d").width == 8
    assert h.port("s").signed and h.port("s").width == 3
    assert h.port("q").width == 12
    h = read_header([HERE / "typed.sv"], "typed", defines={"TYPED_W": "5"})
    assert h.port("s").width == 5


def test_unknown_parameter_rejected():
    with pytest.raises(HeaderError, match=r"no parameter NOPE .*WIDTH"):
        read_header([FIFO], "fw_rv_fifo", {"NOPE": 3})


def test_localparam_override_rejected():
    with pytest.raises(HeaderError, match="W2 is a localparam"):
        read_header([HERE / "nonansi.sv"], "nonansi", {"W2": 3})


def test_missing_module():
    with pytest.raises(HeaderError, match="not found"):
        read_header([FIFO], "no_such_module")


def test_elaboration_error_reported(tmp_path):
    f = tmp_path / "bad.sv"
    f.write_text("module bad(input logic [W-1:0] a); endmodule\n")
    with pytest.raises(HeaderError, match="elaboration errors"):
        read_header([f], "bad")
