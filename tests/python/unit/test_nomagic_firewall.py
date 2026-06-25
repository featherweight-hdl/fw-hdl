"""C4: no-magic firewall — the centralized transparent lowering
(``zuspec.synth.spl``) must never pull in the inferential/scheduling half of
zuspec-synth (scheduler, hazard/forwarding/stall, auto-thread, pipeline).  This
is a regression guard for the "an engineer can imagine how it lowers" principle.
"""
import ast
import pathlib

import zuspec.synth.spl as spl

# Tokens that flag an inferential/scheduling module (REUSE-AUDIT.md "exclude" set).
_FORBIDDEN = (
    "schedule", "scheduler", "sdc_schedule",
    "hazard", "forwarding", "stall", "auto_thread",
    "pipeline", "fsm_extract",
)


def _imported_modules(path: pathlib.Path):
    tree = ast.parse(path.read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_spl_imports_no_scheduling_magic():
    spl_dir = pathlib.Path(spl.__file__).parent
    offenders = []
    for f in sorted(spl_dir.glob("*.py")):
        for mod in _imported_modules(f):
            if any(tok in mod for tok in _FORBIDDEN):
                offenders.append((f.name, mod))
    assert offenders == [], f"no-magic firewall breached: {offenders}"


def test_spl_only_depends_on_ir_core_and_self():
    # Every non-stdlib import is either zuspec.ir.core or spl-local.
    spl_dir = pathlib.Path(spl.__file__).parent
    bad = []
    for f in sorted(spl_dir.glob("*.py")):
        for mod in _imported_modules(f):
            if mod.startswith("zuspec.") and not mod.startswith("zuspec.ir.core"):
                bad.append((f.name, mod))
    assert bad == [], f"spl reached outside ir.core: {bad}"
