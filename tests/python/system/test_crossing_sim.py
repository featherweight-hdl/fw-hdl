"""The domain crossing check as fw_component_root::start() runs it
(design-domains.md §7.5): it prints each crossing and $fatals on an error;
+fw_crossings_nofatal continues, +fw_crossings=<path> writes JSON,
+fw_crossings_off skips it, +fw_crossings_sev overrides a severity.

Builds tests/crossing/crossing_tb.sv once under Verilator and runs it with
+xc_start (one tree with a second root clock across a binding).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fw.hdl.fe.parser import FW_LIB_FILES, FW_LIB_INCDIRS

requires_verilator = pytest.mark.skipif(
    shutil.which("verilator") is None, reason="verilator not installed")

_XC = Path(__file__).resolve().parents[2] / "crossing"


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    work = tmp_path_factory.mktemp("crossing")
    files = list(FW_LIB_FILES) + [str(_XC / "xc_pkg.sv"), str(_XC / "crossing_tb.sv")]
    inc = [f"+incdir+{d}" for d in list(FW_LIB_INCDIRS) + [str(_XC)]]
    b = subprocess.run(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-lint",
                        "-Wno-style", "--top-module", "crossing_tb", "-o", "sim", *inc, *files],
                       cwd=work, capture_output=True, text=True)
    assert b.returncode == 0, f"verilate failed:\n{b.stdout[-3000:]}\n{b.stderr[-3000:]}"

    def run(*plusargs):
        r = subprocess.run([str(work / "obj_dir" / "sim"), "+xc_start", *plusargs],
                           cwd=work, capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout + r.stderr, work
    return run


@requires_verilator
def test_error_is_fatal(sim):
    rc, out, _ = sim()
    assert rc != 0
    assert "fw-hdl crossing [error] clock unrelated binding: top.a.out (clk_b) -> top.b.in_ex (clk_a)" in out
    assert "domain crossing error(s) under 'top'" in out
    assert "continued past the check" not in out


@requires_verilator
def test_nofatal_and_json(sim):
    rc, out, work = sim("+fw_crossings_nofatal", "+fw_crossings=xc.json")
    assert rc == 0, out
    assert "continued past the check" in out
    doc = json.loads((work / "xc.json").read_text())["crossings"]
    assert doc["root"] == "top"
    items = {(i["kind"], i["relation"], i["via"], i["from"]): i for i in doc["items"]}
    x = items[("clock", "unrelated", "binding", "top.a.out")]
    assert (x["severity"], x["to"], x["from_domain"], x["to_domain"], x["waiver"]) == \
        ("error", "top.b.in_ex", "clk_b", "clk_a", "")
    assert ("reset", "unrelated", "reset-sync", "top.a") in items


@requires_verilator
def test_off(sim):
    rc, out, _ = sim("+fw_crossings_off")
    assert rc == 0 and "fw-hdl crossing" not in out


@requires_verilator
def test_severity_override(sim):
    rc, out, work = sim("+fw_crossings_sev=clock:unrelated:warn,reset:sync:info",
                        "+fw_crossings=sev.json")
    assert rc == 0, out
    sev = {i["via"]: i["severity"]
           for i in json.loads((work / "sev.json").read_text())["crossings"]["items"]}
    assert sev == {"binding": "warn", "reset-sync": "info"}
    assert "[warn ] clock unrelated binding" in out
