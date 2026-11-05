"""fw-hdl wrap's inference (fw.hdl.wrap) on made-up module headers: pin
styles, arrays, ambiguity, clock and reset polarity, leftovers, and that an
existing output is never overwritten."""
import pytest

from fw.hdl.rtl_header import Header, HeaderPort
from fw.hdl.wrap import HIGH, LOW, MEDIUM, infer, write_new


def hdr(*ports, params=None):
    return Header("m", dict(params or {}), {}, [],
                  [HeaderPort(n, d, w, f"logic[{w - 1}:0]") for n, d, w in ports])


CLK = [("clk", "in", 1), ("rst", "in", 1)]


def groups(inf):
    return {g.name: (g.kind, g.direction, g.pins, g.confidence) for g in inf.groups}


@pytest.mark.parametrize("pins, want", [
    # the fw kit's template: data ${ep}, ${ep}_valid, ${ep}_ready
    ([("a", "in", 8), ("a_valid", "in", 1), ("a_ready", "out", 1)],
     {"data": "a", "valid": "a_valid", "ready": "a_ready"}),
    # XLS's suffixes, data with _data
    ([("a_data", "out", 8), ("a_vld", "out", 1), ("a_rdy", "in", 1)],
     {"data": "a_data", "valid": "a_vld", "ready": "a_rdy"}),
    # prefixes
    ([("data_a", "in", 4), ("valid_a", "in", 1), ("ready_a", "out", 1)],
     {"data": "data_a", "valid": "valid_a", "ready": "ready_a"}),
])
def test_pin_styles(pins, want):
    inf = infer(hdr(*CLK, *pins))
    (g,) = inf.groups
    assert (g.name, g.kind, g.pins, g.confidence) == ("a", "rv", want, HIGH)


def test_two_data_pins_is_medium():
    inf = infer(hdr(*CLK, ("a", "in", 8), ("a_data", "in", 8), ("a_valid", "in", 1),
                    ("a_ready", "out", 1)))
    g = next(g for g in inf.groups if g.kind == "rv")
    assert g.confidence == MEDIUM and "a_data" in g.why
    assert ("a_data", "level") in [(x.pins["data"], x.kind) for x in inf.groups]


def test_valid_only_output_and_input():
    inf = infer(hdr(*CLK, ("o", "out", 8), ("o_vld", "out", 1),
                    ("i", "in", 8), ("i_vld", "in", 1)))
    g = groups(inf)
    assert g["o"][:2] == ("valid", "out") and g["o"][3] == MEDIUM
    assert g["i"][0] == "level" and g["i_vld"][0] == "level"
    assert any("valid-only input" in t for t in inf.todo)


def test_directions_must_agree():
    """A ready driven the same way as its valid is no handshake."""
    inf = infer(hdr(*CLK, ("a", "in", 8), ("a_valid", "in", 1), ("a_ready", "in", 1)))
    assert {g.kind for g in inf.groups} == {"level"}


def test_numbered_stems_become_an_array():
    pins = [p for i in range(3) for p in ((f"req{i}_data", "in", 8), (f"req{i}_valid", "in", 1),
                                          (f"req{i}_ready", "out", 1))]
    inf = infer(hdr(*CLK, *pins))
    (a,) = inf.arrays
    assert a.name == "req" and len(a.groups) == 3
    assert a.patterns == {"data": "req{i}_data", "valid": "req{i}_valid",
                          "ready": "req{i}_ready"}
    assert inf.groups == []


def test_gap_in_numbers_is_no_array():
    pins = [p for i in (0, 2) for p in ((f"q_{i}", "out", 8), (f"q_{i}_vld", "out", 1),
                                        (f"q_{i}_rdy", "in", 1))]
    inf = infer(hdr(*CLK, *pins))
    assert inf.arrays == [] and sorted(groups(inf)) == ["q_0", "q_2"]


@pytest.mark.parametrize("name, low", [
    ("rst", False), ("rst_i", False), ("reset", False), ("rst_n", True), ("rst_ni", True),
    ("rstn", True), ("aresetn", True), ("nrst", True), ("reset_b", True), ("sys_rst_l", True),
])
def test_reset_polarity(name, low):
    inf = infer(hdr(("clk", "in", 1), (name, "in", 1)))
    assert (inf.reset, inf.reset_active_low) == (name, low)


def test_clock_and_reset_from_the_body():
    body = "always_ff @(posedge ck or negedge rb) if (!rb) q <= 0; else q <= d;"
    inf = infer(hdr(("ck", "in", 1), ("rb", "in", 1)), body)
    assert (inf.clock, inf.reset, inf.reset_active_low) == ("ck", "rb", True)
    assert "body" in inf.clock_why and "negedge" in inf.reset_why
    none = infer(hdr(("ck", "in", 1), ("rb", "in", 1)))
    assert none.clock is None and any("no clock" in t for t in none.todo)


def test_leftovers():
    inf = infer(hdr(*CLK, ("dbg_q", "out", 4), ("scan_en", "in", 1), ("mode", "in", 2),
                    ("name", "out", 1), ("bus", "inout", 8)))
    assert inf.opens == [("dbg_q", "debug-like output, left open")]
    assert inf.ties == [("scan_en", 0, "debug-like input, tied to 0")]
    g = groups(inf)
    assert g["mode"][:2] == ("level", "in") and g["mode"][3] == LOW
    assert g["name_p"][:2] == ("level", "out")              # a reserved name is renamed
    assert any("inout pin bus" in t for t in inf.todo)


def test_never_overwrites(tmp_path):
    p = tmp_path / "w.svh"
    assert write_new(str(p), "a\n") == (True, "")
    assert write_new(str(p), "a\n") == (True, "")           # the same: fine
    p.write_text("a\n// edited\n")
    ok, diff = write_new(str(p), "b\n")
    assert not ok and "+b" in diff and "-// edited" in diff
    assert p.read_text() == "a\n// edited\n" and (tmp_path / "w.svh.new").read_text() == "b\n"
