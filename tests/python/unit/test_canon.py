"""Canonical comparison of two views under a contract."""
import json

import pytest

from fw.hdl.verif.canon import Event, Rule, canonical, check, compare, load_trace


def tr(spec, cyc0=0):
    """'i1:k:c:d o1:d ...' -> events; ids are ints, key/cls/data default 0."""
    out = []
    for n, tok in enumerate(spec.split()):
        ev, rest = tok[0], tok[1:].split(":")
        f = [int(x) for x in rest] + [0] * 3
        if ev == "i":
            out.append(Event("p", "in", cyc0 + n, f[0], f[1], f[2], f[3]))
        else:
            out.append(Event("p", "out", cyc0 + n, f[0], data=f[1]))
    return out


PER_KEY = Rule(per_key=True)


def test_in_order_equivalent_only_if_same_sequence():
    a = tr("i1 i2 o1 o2")
    b = tr("i1 o1 i2 o2")          # different timing, same order
    assert compare(a, b, Rule()) == []
    c = tr("i1 i2 o2 o1")
    assert any("REORDER" in d for d in compare(a, c, Rule()))


def test_per_key_cross_key_reorder_is_the_same_function():
    a = tr("i1:10 i2:20 i3:10 o1 o2 o3")
    b = tr("i1:10 i2:20 i3:10 o2 o1 o3")
    assert compare(a, b, PER_KEY) == []
    assert canonical(a, PER_KEY) == canonical(b, PER_KEY)


def test_per_key_same_key_reorder_is_caught():
    a = tr("i1:10 i3:10 o3 o1")
    assert check(a, PER_KEY) == ["REORDER: id 3 left before earlier id 1"]


def test_class_pass():
    r = Rule(allow_pass=frozenset({(0, 1)}))
    a = tr("i1:0:0 i2:0:1 o1 o2")
    b = tr("i1:0:0 i2:0:1 o2 o1")
    assert compare(a, b, r) == []
    c = tr("i1:0:1 i2:0:0 o2 o1")
    assert check(c, r) == ["REORDER: id 2 left before earlier id 1"]


def test_data_lost_unknown_duplicate():
    assert check(tr("i1:0:0:5 o1:6"), Rule()) == ["DATA: id 1 left with 0x6, entered with 0x5"]
    assert check(tr("i1 i2 o1"), Rule()) == ["LOST: id 2 never left"]
    assert check(tr("o4"), Rule()) == ["UNKNOWN: id 4 left but never entered"]
    assert check(tr("i1 i1"), Rule())[0].startswith("DUPLICATE")


def test_item_difference_between_views():
    d = compare(tr("i1:0:0:5 o1:5"), tr("i1:0:0:7 o1:7"), Rule(), names=("model", "rtl"))
    assert d == ["item 1: model=5 rtl=7"]


def test_strict_after():
    r = Rule(strict_after=frozenset({(0, 1)}))
    ok = [Event("p", "in", 0, 1, cls=0), Event("p", "in", 0, 2, cls=1),
          Event("p", "out", 5, 1), Event("p", "out", 6, 2)]
    bad = ok[:2] + [Event("p", "out", 5, 1), Event("p", "out", 5, 2)]
    assert check(ok, r) == []
    assert check(bad, r) == ["SAME_CYCLE: id 2 left in cycle 5 with earlier id 1"]


def test_pinned_cycles():
    r = Rule(pin_cycles=True)
    a = tr("i1 o1")
    b = tr("i1 i9 o1")[:1] + [Event("p", "out", 7, 1)]
    assert "leave cycles differ" in " ".join(compare(a, b, r))


def test_load_trace_and_rule(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in [
        {"pt": "a", "ev": "in", "cyc": 1, "id": 1, "key": 0, "cls": 0, "data": 3},
        {"pt": "b", "ev": "out", "cyc": 4, "id": 1, "key": 0, "cls": 0, "data": 3}]) + "\n")
    assert check(load_trace(p), Rule.from_dict({"per_key": True})) == []
    with pytest.raises(ValueError):
        Rule.from_dict({"perkey": True})
