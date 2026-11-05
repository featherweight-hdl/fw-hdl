"""Characterization facts: sidecar files, port wildcards, overlays and their
provenance, conflicts and the unverified flag."""
import textwrap

import pytest

import zuspec.ir.core as ir
from zuspec.ir.core.results import Overlay, ResultStore

from fw.hdl.facts import (BlockFact, FactsError, check_value, expand, latency_range,
                          load_sidecar, overlay, unverified)

PORTS = ["req_0", "req_1", "req_2", "rsp"]


def _ports():
    u8 = ir.DataTypeInt(bits=8, signed=False)
    return {n: ir.Field(name=n, datatype=(ir.DataTypePutIF if n == "rsp" else ir.DataTypeGetIF)(
        element_type=u8)) for n in PORTS}


def lat(src, dst, **v):
    f = BlockFact("iface.latency", {"src": src, "dst": dst, **v})
    check_value(f)
    return f


def test_sidecar(tmp_path):
    p = tmp_path / "ext_q.facts.yaml"
    p.write_text(textwrap.dedent("""\
        format: fw-hdl.facts
        version: 1
        blocks:
          - class: ext_q
            facts:
              - {kind: latency, src: "req[*]", dst: rsp, min: 3, max: 40}
              - {kind: ii, port: "req[1]", n: 2}
              - {kind: area, value: 18500, unit: um2, source: "datasheet rev 2"}
        """))
    [(cls, facts)] = load_sidecar(str(p))
    assert cls == "ext_q"
    assert [f.kind for f in facts] == ["iface.latency", "iface.ii", "area.estimate"]
    out = [e for f in facts for e in expand(f, PORTS)]
    assert [(e.kind, e.value.get("src", e.value.get("port"))) for e in out] == [
        ("iface.latency", "req_0"), ("iface.latency", "req_1"), ("iface.latency", "req_2"),
        ("iface.ii", "req_1"), ("area.estimate", None)]


def test_sidecar_bad_kind(tmp_path):
    p = tmp_path / "x.facts.yaml"
    p.write_text("format: fw-hdl.facts\nversion: 1\nblocks:\n"
                 "  - class: ext_q\n    facts:\n      - {kind: speed, port: rsp}\n")
    with pytest.raises(FactsError, match="speed"):
        load_sidecar(str(p))


@pytest.mark.parametrize("value,msg", [
    ({"src": "nope", "dst": "rsp", "fixed": 1}, "not a port"),
    ({"src": "ack[*]", "dst": "rsp", "fixed": 1}, "matches no port"),
    ({"src": "req_0", "fixed": 1}, "no 'dst'"),
])
def test_expand_errors(value, msg):
    with pytest.raises(FactsError, match=msg):
        expand(BlockFact("iface.latency", value), PORTS)


@pytest.mark.parametrize("value,msg", [
    ({"fixed": 1, "min": 1}, "not both"),
    ({}, "give fixed"),
    ({"min": 4, "max": 2}, "min 4 > max 2"),
])
def test_latency_values(value, msg):
    with pytest.raises(FactsError, match=msg):
        lat("req_0", "rsp", **value)


def test_latency_max_alone_means_at_least_zero():
    f = lat("req_0", "rsp", max=7)
    assert f.value["min"] == 0 and latency_range(f.value) == (0, 7)


def test_overlay_round_trip_and_ranking(tmp_path):
    ports = _ports()
    decl, anchors = overlay("ext_q", ports, [lat("req_0", "rsp", min=1, max=4)])
    meas, _ = overlay("ext_q", ports, [lat("req_0", "rsp", fixed=6)], provenance="measured")
    decl.save(str(tmp_path / "d.json"))
    back = Overlay.load(str(tmp_path / "d.json"))
    assert back.header.provenance == "declared"
    assert [f.value for f in back.facts("iface.latency")] == [
        {"src": "req_0", "dst": "rsp", "min": 1, "max": 4}]
    s = ResultStore(anchors)
    s.add(back)
    s.add(meas)
    [c] = s.conflicts()
    assert c.higher.overlay.header.provenance == "measured"
    assert "declared" in str(c) and "measured" in str(c)


def test_unverified():
    d = lat("req_0", "rsp", min=1, max=4)
    assert unverified(d, [])
    assert unverified(d, [lat("req_1", "rsp", fixed=2)])          # other ports
    assert unverified(d, [lat("req_0", "rsp", fixed=6)])          # outside the range
    assert not unverified(d, [lat("req_0", "rsp", min=2, max=3)])
    ii = BlockFact("iface.ii", {"port": "req_0", "n": 1})
    assert not unverified(ii, [BlockFact("iface.ii", {"port": "req_0", "n": 1})])
