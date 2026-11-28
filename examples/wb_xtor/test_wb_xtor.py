"""The Wishbone protocol package on the canonical API: examples/wb_xtor.
test_sim runs its bench under Verilator on fw-hdl-rt-sv: wb_initiator and
wb_target back to back, plain and with random wait states, and two mutants
the checks must catch. test_static elaborates the bench with fw-hdl-fe-sv
and checks the protocol table and the API bindings. test_mixed lowers
wb_initiator to RTL (its crossings as ready/valid ports) and runs it in the
same bench: the results are the class model's. test_plain runs the
generated shells with plain bridges (no fw-hdl) from plain class code.
test_cocotb runs the class bench in cocotb on the generated cores, with no
SV interface or shell, through generated cocotb bridges: the results are
the class model's.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_EX = Path(__file__).resolve().parent


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_sim(tmp_path):
    r = subprocess.run(["sh", "scripts/run_sim.sh"], cwd=_EX,
                       env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    res = [l for l in out.splitlines() if l.startswith(("R ", "D "))]
    assert res == [
        "R ok 40 accesses in 149 edges, 7 back to back",
        "R ok 40 accesses in 185 edges, 7 back to back",
        "R fail access 0: stb still high at edge 6 (drop)",
        "R fail access 2: read 00000000, expected 20000002",
    ], out[-3000:]


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_mixed(tmp_path):
    r = subprocess.run(["sh", "scripts/run_mixed.sh"], cwd=_EX,
                       env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    res = [l for l in out.splitlines() if l.startswith(("R ", "D "))]
    assert res == [
        "R ok 40 accesses in 149 edges, 7 back to back",
        "R ok 40 accesses in 185 edges, 7 back to back",
        "R fail access 2: read 00000000, expected 20000002",
    ], out[-3000:]
    rtl = (tmp_path / "gen" / "wb_initiator_rtl.sv").read_text()
    assert "always_ff" not in rtl            # step only hands off: all comb


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_shell_ref(tmp_path):
    # T0 of docs/design/xtor-shell-plan.md: the hand-written shell
    # (core + interface) and bridge in place of the class initiator.
    r = subprocess.run(["sh", "shell_ref/run_shell.sh", "init"], cwd=_EX,
                       env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    res = [l for l in out.splitlines() if l.startswith(("R ", "D "))]
    assert res == [
        "R ok 40 accesses in 149 edges, 7 back to back",
        "R ok 40 accesses in 185 edges, 7 back to back",
        "R fail access 2: read 00000000, expected 20000002",
    ], out[-3000:]


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_shell_ref_tgt(tmp_path):
    # T5 of docs/design/xtor-shell-plan.md: the hand-written target shell
    # (core + interface) and bridge in place of the class target; the
    # class initiator's mutant (+mut_init) must still fail.
    r = subprocess.run(["sh", "shell_ref/run_shell.sh", "tgt"], cwd=_EX,
                       env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    res = [l for l in out.splitlines() if l.startswith(("R ", "D "))]
    assert res == [
        "R ok 40 accesses in 149 edges, 7 back to back",
        "R ok 40 accesses in 185 edges, 7 back to back",
        "R fail access 0: stb still high at edge 6 (drop)",
    ], out[-3000:]


_RESULTS = {
    "init": ["R ok 40 accesses in 149 edges, 7 back to back",
             "R ok 40 accesses in 185 edges, 7 back to back",
             "R fail access 2: read 00000000, expected 20000002"],
    "tgt": ["R ok 40 accesses in 149 edges, 7 back to back",
            "R ok 40 accesses in 185 edges, 7 back to back",
            "R fail access 0: stb still high at edge 6 (drop)"],
}


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
@pytest.mark.parametrize("which", ["init", "tgt"])
def test_shell_gen(tmp_path, which):
    # T3/T4 of docs/design/xtor-shell-plan.md: the interface, shell and
    # bridge generated from the IR (emit_xtor) give the hand-written ones'
    # results, and lint clean under -Wall with the core.
    r = subprocess.run(["sh", "shell_ref/run_shell.sh", which], cwd=_EX,
                       env={**os.environ, "OUT": str(tmp_path), "GEN": "1"},
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    res = [l for l in out.splitlines() if l.startswith(("R ", "D "))]
    assert res == _RESULTS[which], out[-3000:]
    x = {"init": "wb_initiator", "tgt": "wb_target"}[which]
    files = [f for f in (tmp_path / "gen" / "files.f").read_text().split()
             if not f.endswith("_lowered.sv")]
    lint = subprocess.run(["verilator", "--lint-only", "-Wall", "--top-module",
                           f"{x}_xtor"] + files, capture_output=True, text=True, timeout=300)
    assert lint.returncode == 0, (lint.stdout + lint.stderr)[-3000:]
    # T4: the generated bridge, with the class code it needs; -Wall warns
    # only in the runtime and the example's own package, not the bridge
    pk = Path(os.environ["IVPM_PACKAGES"])
    g = tmp_path / "gen"
    lint = subprocess.run(
        ["verilator", "--lint-only", "-Wall", "--top-module", f"{x}_xtor",
         f"-I{pk / 'fw-hdl-rt-sv/sv'}", f"-I{pk / 'fw-hdl-spec/bindings/sv'}",
         f"-I{pk / 'fw-hdl-spec/std'}", f"-I{_EX / 'src'}", f"-I{g}",
         str(pk / "fw-hdl-rt-sv/sv/fw_hdl_pkg.sv"), str(_EX / "src/wb_api_pkg.sv"), str(_EX / "src/wb_pkg.sv")]
        + files + [str(g / f"{x}_bridge_pkg.sv")],
        capture_output=True, text=True, timeout=300)
    out = lint.stdout + lint.stderr
    bad = [l for l in out.splitlines()
           if (l.startswith("%Error") and "Exiting due to" not in l)
           or (l.startswith("%Warning") and str(g) in l)]
    assert bad == [], out[-3000:]


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
def test_plain(tmp_path):
    # T4c of docs/design/xtor-shell-plan.md (D10): both generated shells
    # back to back, driven through plain bridges from class code with no
    # fw-hdl on the command line; +mut_mem must fail, and the target's
    # run() must stop with $fatal when set_p() was not called.
    r = subprocess.run(["sh", "plain/run_plain.sh"], cwd=_EX,
                       env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    res = [l for l in out.splitlines() if l.startswith("R ")]
    assert res == [
        "R ok 40 accesses in 79 edges",
        "R ok 40 accesses in 164 edges",
        "R fail access 20: read 10000001, expected 10000000",
    ], out[-3000:]
    assert "run() with port 'p' unset (call set_p())" in out, out[-3000:]
    # the plain bridges: no fw-hdl, and clean under -Wall
    br = [tmp_path / "gen_init" / "wb_initiator_bridge.svh",
          tmp_path / "gen_tgt" / "wb_target_bridge.svh"]
    for b in br:
        assert "fw_" not in b.read_text(), b.read_text()
    files = [f for w in ("init", "tgt")
             for f in (tmp_path / f"gen_{w}" / "files.f").read_text().split()
             if not f.endswith("_lowered.sv")]
    lint = subprocess.run(
        ["verilator", "--lint-only", "-Wall", "--top-module", "wb_plain_tb",
         f"-I{_EX / 'src'}", f"-I{_EX / 'plain'}", f"-I{tmp_path / 'gen_init'}",
         f"-I{tmp_path / 'gen_tgt'}", str(_EX / "src/wb_api_pkg.sv")] + files +
        [str(tmp_path / "gen_init/wb_initiator_bridge_pkg.sv"),
         str(tmp_path / "gen_tgt/wb_target_bridge_pkg.sv")] +
        [str(_EX / "plain" / f) for f in ("wb_plain_clk_if.sv", "wb_plain_tb_pkg.sv",
                                          "wb_plain_tb.sv")],
        capture_output=True, text=True, timeout=300)
    msgs = [l for l in lint.stderr.splitlines() if l.startswith("%Warning")]
    assert not [m for m in msgs if "_bridge" in m], lint.stderr[-3000:]


@pytest.mark.skipif(shutil.which("verilator") is None, reason="verilator not installed")
@pytest.mark.skipif(importlib.util.find_spec("cocotb") is None, reason="cocotb not installed")
def test_cocotb(tmp_path):
    # T7 of docs/design/xtor-shell-plan.md (D9): the class bench's driver,
    # memory and checks in cocotb, on the two generated cores through their
    # generated cocotb bridges; the same results as the class bench.
    r = subprocess.run([sys.executable, "cocotb/run_cocotb.py"], cwd=_EX,
                       env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    res = [l for l in out.splitlines() if l.startswith("R ")]
    assert res == [
        "R ok 40 accesses in 149 edges, 7 back to back",
        "R ok 40 accesses in 185 edges, 7 back to back",
        "R fail access 1: read 00000001, expected 00000000",
        "R fail wb_target_bridge: run() with port 'p' unset (call set_p())",
    ], out[-3000:]
    # no interface or shell: the cores only
    gen = sorted(f.name for f in (tmp_path / "gen_init").iterdir())
    assert "wb_initiator_xtor_if.sv" not in gen and "wb_initiator_bridge.py" in gen, gen


def test_static():
    r = subprocess.run([sys.executable, "scripts/elab_check.py"], cwd=_EX,
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    d = json.loads(r.stdout)
    assert d["diags"] == []
    p = d["protocols"]["wb_proto#(32,32)"]
    assert (p["family"], p["params"]) == ("wb_proto", {"AW": 32, "DW": 32})
    assert p["apis"] == [{"dir": "req", "type": "wb_if#(32,32)"}]
    assert p["bundles"] == ["wb_bundle#(32,32)"]
    assert sorted((c["type"], c["role"]) for c in p["converters"]) == [
        ("wb_initiator#(32,32)", "initiator"), ("wb_target#(32,32)", "target")]
    assert sorted((b["from"], b["to"]) for b in d["bindings"]) == [
        ("top.d.p", "top.xi.t"), ("top.xt.p", "top.m.t")]


def _xtor_ir(src, top):
    from fw.hdl.fe.sv import elaborate
    r = elaborate([str(_EX / "src" / "wb_api_pkg.sv"), str(_EX / "src" / "wb_pkg.sv"), str(_EX / "tb" / src)], top=top,
                  incdirs=[str(_EX / "src")], lower=True)
    assert r.ok, "\n".join(map(str, r.diags))
    return r.to_ir()[0]


def _calls(body):
    """Each awaited call in *body* (loops flattened) as
    (receiver, method, args): a field by name, an endpoint as [path]."""
    import zuspec.ir.core as ir
    out = []
    for s in body:
        if isinstance(s, ir.StmtWhile):
            out.append(("while", _calls(s.body)))
        elif isinstance(s, ir.StmtExpr) and isinstance(s.expr, ir.ExprAwait):
            c = s.expr.value
            v = c.func.value
            out.append((v.index if isinstance(v, ir.ExprRefField)
                        else [e.name for e in v.elements], c.func.attr,
                        [a.name for a in c.args]))
    return out


def test_task_code_ir():
    """T1/T2 of docs/design/xtor-shell-plan.md: what the bridge generator
    reads from the IR. The task code: the initiator's access() and the
    target's run(), as the hand-written bridges in shell_ref/ have them;
    the crossings are recorded once lowered (emit_core.py)."""
    import zuspec.ir.core as ir
    ini = _xtor_ir("wb_emit.sv", "wb_emit_pkg::top").type_m["wb_initiator"]
    fx = {f.name: i for i, f in enumerate(ini.fields)}
    (a,) = [b for b in ini.proc_blocks if b.kind == ir.ProcKind.TASK]
    assert a.name == "access"
    assert [(x.arg, x.direction.name) for x in a.args] == [("rsp", "OUTPUT"), ("req", "INPUT")]
    assert _calls(a.body) == [(fx["reqs"], "put", ["req"]), (fx["rsps"], "get", ["rsp"])]
    tgt = _xtor_ir("wb_emit_tgt.sv", "wb_emit_tgt_pkg::top").type_m["wb_target"]
    fx = {f.name: i for i, f in enumerate(tgt.fields)}
    (r,) = [b for b in tgt.proc_blocks if b.kind == ir.ProcKind.TASK]
    assert (r.name, r.args) == ("run", [])
    assert _calls(r.body) == [("while", [(fx["reqs"], "get", ["r"]), (["p"], "access", ["s", "r"]),
                                         (fx["rsps"], "put", ["s"])])]


def test_task_code_lowered(tmp_path):
    """Lowering keeps the task code (task_blocks), a crossing named by its
    sync_xings path; the API method is a task (is_async, as a Python
    async def)."""
    import zuspec.ir.core as ir
    from fw.hdl.fe.sv.emit import emit_sv
    for src, top, cls in (("wb_emit.sv", "wb_emit_pkg::top", "wb_initiator"),
                          ("wb_emit_tgt.sv", "wb_emit_tgt_pkg::top", "wb_target")):
        from fw.hdl.fe.sv import elaborate
        r = elaborate([str(_EX / "src" / "wb_api_pkg.sv"), str(_EX / "src" / "wb_pkg.sv"), str(_EX / "tb" / src)], top=top,
                      incdirs=[str(_EX / "src")], lower=True)
        assert r.ok, "\n".join(map(str, r.diags))
        ctxt, t = r.to_ir()
        (m,) = ctxt.type_m["wb_if"].body.methods
        assert (m.name, m.is_async) == ("access", True)
        emit_sv(ctxt, t, tmp_path / cls, top_module=f"{cls}_low",
                rename={cls: f"{cls}_core"})
        core = ctxt.type_m[f"{cls}_core"]
        assert ["/".join(x.path) for x in core.sync_xings] == ["reqs", "rsps"]
        assert all(b.kind != ir.ProcKind.TASK for b in core.proc_blocks)
        (b,) = core.task_blocks
        if cls == "wb_initiator":
            assert _calls(b.body) == [(["reqs"], "put", ["req"]), (["rsps"], "get", ["rsp"])]
        else:
            assert _calls(b.body) == [("while", [(["reqs"], "get", ["r"]),
                                                 (["p"], "access", ["s", "r"]),
                                                 (["rsps"], "put", ["s"])])]
