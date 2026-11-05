"""Constructs that wrapped IP (an extern's port map) and the component factory
rely on, run by the elaboration interpreter and by the simulator with the same
results: interface-class dispatch, port handles passed as their untyped base
(fw_endpoint), $sformatf, queues and associative arrays, static members of
parameterized classes whose initializer reads themselves, static methods
through a typedef (`T::type_id::make`), and a string-keyed override.
"""
from pathlib import Path

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab import hier
from fw.hdl.xls_flow import _find_class, _parse
from xls_harness import have_verilator, run_verilator

HERE = Path(__file__).resolve().parent / "extern"
PKG = HERE / "probe_pkg.sv"


def _field(o, name):
    return next(v for k, v in o.fields.items() if k.name == name)


@pytest.fixture(scope="module")
def parser():
    return _parse([str(PKG)], FlowConfig(), ErrorReporter())


def _elab(parser, top, monkeypatch):
    its = []
    init = hier._Recorder.__init__

    def keep(self, *a, **k):
        init(self, *a, **k)
        its.append(self)
    monkeypatch.setattr(hier._Recorder, "__init__", keep)
    cls = _find_class(parser, top)
    node = hier.elaborate_tree(cls.compilation, cls, top)
    rec = next(v for k, v in its[-1].statics.items() if k.name == "r")
    return node, rec


def test_interface_dispatch_and_port_handles(parser, monkeypatch):
    node, rec = _elab(parser, "top_iface", monkeypatch)
    assert _field(rec, "names") == ["W", "req0", "req1", "gnt"]
    assert _field(rec, "vals") == {"W": 7}
    ends = _field(rec, "ends")
    assert [_field(e, "m_ep_name") for e in ends] == ["in[0]", "in[1]", "out"]
    # each handle is the child's own port object
    u = node.children["u"]
    assert {e.oid for e in ends} == {p.obj.oid for p in u.ports.values()}


def test_static_registry_and_override(parser, monkeypatch):
    node, rec = _elab(parser, "top_factory", monkeypatch)
    assert node.children["u"].cls.name == "leaf2"     # declared leaf_f, overridden
    assert _field(rec, "names") == ["SUB"]


@pytest.mark.verilator
@pytest.mark.skipif(not have_verilator(), reason="needs verilator")
def test_simulator_agrees(tmp_path):
    out = run_verilator([PKG, HERE / "probe_tb.sv"], "probe_tb", tmp_path)
    text = "\n".join(out)
    assert "W=7 ends=3" in text
    assert "iface end 0 in[0]" in text and "iface end 2 out" in text
    assert "factory leaf2=1" in text and '"SUB"' in text
