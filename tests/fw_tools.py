"""Find the tools the tests run: dfm, pytest, verilator, yosys, sby, ...

The tests used to look only in ``REPO/packages/<pkg>/bin``, where ``ivpm
update`` puts them in a standalone checkout. When fw-hdl is itself a package
of another project (``<project>/packages/fw-hdl``) that directory does not
exist, so tests were skipped silently. ``tool()`` looks, in order:

1. ``$FW_HDL_<NAME>`` (e.g. ``FW_HDL_DFM``, ``FW_HDL_VERILATOR``);
2. ``REPO/packages/<pkg>/bin/<name>`` (a standalone checkout), then
   ``REPO/../<pkg>/bin/<name>`` when fw-hdl is itself in an ivpm
   ``packages/`` directory;
3. for Python entry points (dfm, pytest), the bin directory of the running
   interpreter, so dfm comes from the environment fw.hdl is installed in;
4. ``PATH``.

When nothing is found it returns the ``REPO/packages`` path anyway, so a
caller's ``.exists()`` check is false and its skip reason still names it.
"""
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# tool -> the ivpm package that provides it
_PKG = {
    "dfm": "python", "pytest": "python",
    "verilator": "verilator",
    "yosys": "yosys", "sby": "yosys", "z3": "yosys", "boolector": "yosys",
}
_PY_TOOLS = {"dfm", "pytest"}


def tool(name: str, pkg: str = None) -> Path:
    """The path of tool *name* (see the module docstring for the search order)."""
    env = os.environ.get("FW_HDL_" + name.upper().replace("-", "_"))
    if env:
        return Path(env)
    own = REPO / "packages" / (pkg or _PKG.get(name, name)) / "bin" / name
    if own.is_file():
        return own
    if REPO.parent.name == "packages":      # fw-hdl is a package of an ivpm workspace
        ws = REPO.parent / (pkg or _PKG.get(name, name)) / "bin" / name
        if ws.is_file():
            return ws
    if name in _PY_TOOLS:
        # not resolved: a venv's python is a symlink out of the venv
        cand = Path(sys.executable).parent / name
        if cand.is_file():
            return cand
    found = shutil.which(name)
    if found:
        return Path(found)
    return own


def have(name: str, pkg: str = None) -> bool:
    return tool(name, pkg).is_file()
