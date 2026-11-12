"""Canary: one GCD through two front ends.

SV (fw-hdl) and Python (zuspec-dataclasses) versions of the same function
must give the same anchors for what the user wrote (docs/anchors.md P1/P2),
the same block interface, and the same schedule on those anchors, through
zuspec-be-xls and XLS. Lives in fw-hdl, not zuspec-be-xls as the plan said:
the SV half needs fw-hdl's front end, and be-xls must not depend on it.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

zdc = pytest.importorskip("zuspec.dataclasses")

from zuspec.be.xls import xir
from zuspec.be.xls.lower_fn import lower_functions
from zuspec.ir.core.anchor import assign_anchors
from zuspec.ir.core.results.kinds import validate

from fw.hdl.xls_flow import sv_to_functions
from test_xls_overlay import needs_xls, overlay_of, run_xls

HERE = Path(__file__).parent / "canary"
TOP = "gcd_euclidean8"
VALID = ["--input_valid_signal=input_valid", "--output_valid_signal=output_valid"]


def sv_fns():
    return sv_to_functions([str(HERE / "gcd_canary_pkg.sv")], [f"gcd_canary_pkg::{TOP}"],
                           rename={f"gcd_canary_pkg::{TOP}": TOP})


def zdc_fns():
    from zuspec.dataclasses.data_model_factory import DataModelFactory
    spec = importlib.util.spec_from_file_location("gcd_zdc_canary", HERE / "gcd_zdc.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    ctx = DataModelFactory().build(mod.Gcd)
    return [f for f in ctx.type_m["Gcd"].functions if f.name in (TOP, "gcd_euclidean")]


def user(table):
    """Anchors of nodes the user wrote (synthesized ones carry `x:`)."""
    return {a for a in table if "x:" not in a}


def build(fns, workdir):
    table = assign_anchors(fns)
    pkg = xir.Package(name=TOP)
    lower_functions(pkg, fns)
    pkg.top = TOP
    return table, overlay_of(table, run_xls(pkg, workdir, 2, TOP, VALID))


def test_a_user_anchors_are_the_same():
    sv, z = user(assign_anchors(sv_fns())), user(assign_anchors(zdc_fns()))
    assert sv == z, (sorted(sv - z), sorted(z - sv))


@needs_xls
@pytest.mark.xfail(strict=True, reason=(
    "zuspec-dataclasses gap: its data-model factory builds Arg without a "
    "datatype (data_model_factory.py, Arg(arg=, annotation=)), so the XLS "
    "engine adapter rightly rejects the zdc half ('argument has no type'). "
    "Typing is the front end's job; drop this once zdc resolves Arg.datatype."))
def test_bcd_interface_schedule_and_validity(tmp_path):
    ts, os_ = build(sv_fns(), tmp_path / "sv")
    tz, oz = build(zdc_fns(), tmp_path / "zdc")
    # (b) the same block interface
    assert os_.column("iface.block")["value"] == oz.column("iface.block")["value"]
    # (c) the same stage for every user anchor both schedule
    def stages(o):
        c = o.column("sched.stage")
        out = {}
        for a, v in zip(c["anchor"], c["value"]):
            if "x:" not in a:
                out.setdefault(a, set()).add(v)
        return out
    assert stages(os_) and stages(os_) == stages(oz)
    # (d) both overlays validate
    for o in (os_, oz):
        for f in o.facts():
            validate(f)
