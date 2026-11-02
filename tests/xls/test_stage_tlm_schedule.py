"""fw.hdl.xls.StageTLM reads XLS schedules through zuspec-be-xls's reader
(phase0-plan.md D4): same stages, length and period as before."""
from fw.hdl.stage_tlm import parse_schedules, stage_table

TEXT = """
schedules {
  key: "dec"
  value {
    function: "dec"
    stages {
      stage: 0
      timed_nodes { node: "a" node_delay_ps: 0 path_delay_ps: 0 }
      timed_nodes { node: "add.3" node_delay_ps: 5 path_delay_ps: 5 }
    }
    stages {
      stage: 1
    }
    stages {
      stage: 2
      timed_nodes { node: "out" node_delay_ps: 1 path_delay_ps: 1 }
    }
    min_clock_period_ps: 13
    length: 3
  }
}
"""


def test_stages_length_period_and_empty_stages():
    s = parse_schedules(TEXT)["dec"]
    assert s.length == 3 and s.min_clock_period_ps == 13
    assert s.stages == {0: ["a", "add.3"], 1: [], 2: ["out"]}
    assert s.clks() == 5
    assert stage_table(s).splitlines()[1:] == ["0 a", "0 add.3", "2 out"]


def test_schedule_from_bundle_matches_the_textproto(tmp_path):
    """D4: the overlay gives StageTLM the same length and period as the
    schedule file, and the same stage for every node it anchors."""
    import pytest
    from test_xls_overlay import GCD, needs_xls, overlay_of, run_xls
    from zuspec.be.xls.read_schedule import parse_schedules as read
    from zuspec.be.xls.testing.xlstools import codegen_main
    from zuspec.ir.core.results import write_bundle
    from fw.hdl.stage_tlm import schedule_from_bundle
    from fw.hdl.xls_flow import sv_function_package, sv_to_functions
    from zuspec.ir.core.anchor import assign_anchors
    if codegen_main() is None:
        pytest.skip("XLS tools not found")
    top, module = "gcd_pkg::gcd_binary8", "gcd_pkg__gcd_binary8"
    fns = sv_to_functions(GCD, [top], rename={top: module})
    table = assign_anchors(fns)
    from zuspec.be.xls import xir
    from zuspec.be.xls.lower_fn import lower_functions
    pkg = xir.Package(name=module)
    lower_functions(pkg, fns)
    pkg.top = module
    art = run_xls(pkg, tmp_path / "xls", 2, module)
    write_bundle(str(tmp_path / f"{module}.zir"), table, [overlay_of(table, art)])
    got = schedule_from_bundle(str(tmp_path / f"{module}.zir"))
    want = parse_schedules(art["sched"])[module]
    raw = read(art["sched"])[module]
    assert got.function == module
    assert (got.length, got.min_clock_period_ps) == (want.length, want.min_clock_period_ps)
    assert got.clks() == want.clks()
    # Exit criterion 5: the same Schedule, so stage_tlm_sv writes the same SV.
    assert got == want, (got.stages, want.stages)
    assert stage_table(got) == stage_table(want)
