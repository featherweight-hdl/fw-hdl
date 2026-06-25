"""pyslang wrapper for the fw-hdl front end.

Written against the **pyslang 11** namespaced API (``pyslang.syntax`` /
``pyslang.ast``) — the flat ``pyslang.SyntaxTree`` form used by some older code
does not exist in this version.

The parser auto-includes the fw-hdl library compilation units (the
``fw_hdl_pkg`` / ``fw_std_pkg`` packages plus the ``fw_clock_xtor_if`` /
``fw_put_xtor_if`` interfaces and the ``fw_root`` module) and their include
directories, so a design that ``import``s ``fw_hdl_pkg`` / ``fw_std_pkg``
elaborates cleanly.  This set was verified to produce a zero-error compilation
of the blinky example.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import pyslang
from pyslang import ast, syntax

from ..config import FlowConfig
from ..errors import ErrorReporter

# Repo root: python/fw/hdl/fe/parser.py -> parents[4] == <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "src"
_STD = _SRC / "std"

# fw-hdl library compilation units, in dependency order (packages + the
# interface/module units the packages and tops reference).
FW_LIB_FILES: List[str] = [
    str(_SRC / "fw_clock_xtor_if.sv"),
    str(_SRC / "fw_hdl_pkg.sv"),
    str(_SRC / "fw_root.sv"),
    str(_STD / "fw_put_xtor_if.sv"),
    str(_STD / "fw_std_pkg.sv"),
]

# Include directories needed to resolve the library `include directives.
FW_LIB_INCDIRS: List[str] = [str(_SRC), str(_STD)]


class Parser:
    """Parses SystemVerilog into a pyslang :class:`~pyslang.ast.Compilation`."""

    def __init__(self, config: FlowConfig, reporter: ErrorReporter):
        self.config = config
        self.reporter = reporter
        self.compilation: Optional[ast.Compilation] = None
        self.source_manager: Optional[pyslang.SourceManager] = None
        # Keep strong refs to SyntaxTrees: the C++ Compilation holds raw pointers.
        self._trees: List[syntax.SyntaxTree] = []

    # -- options ---------------------------------------------------------
    def _make_options(self, extra_incdirs: List[str]) -> pyslang.Bag:
        pp = pyslang.parsing.PreprocessorOptions()
        pp.predefines = list(self.config.predefine_strings())
        pp.additionalIncludePaths = list(extra_incdirs)
        bag = pyslang.Bag()
        bag.preprocessorOptions = pp
        return bag

    def _make_source_manager(self, incdirs: List[str]) -> pyslang.SourceManager:
        sm = pyslang.SourceManager()
        for d in incdirs:
            if d:
                sm.addUserDirectories(d)
        return sm

    # -- parsing ---------------------------------------------------------
    def parse(self, files: List[str], *, include_lib: bool = True) -> bool:
        """Parse *files* (plus the fw-hdl library unless ``include_lib`` is False).

        Returns True on a zero-error compilation.
        """
        incdirs = list(FW_LIB_INCDIRS) if include_lib else []
        incdirs += list(self.config.incdirs)
        # Design directories are implicit include paths too.
        incdirs += sorted({os.path.dirname(os.path.abspath(f)) for f in files})

        try:
            self.source_manager = self._make_source_manager(incdirs)
            options = self._make_options(incdirs)
            self.compilation = ast.Compilation()
            self._trees = []

            lib_files = list(FW_LIB_FILES) if include_lib else []
            for path in lib_files + list(files):
                tree = syntax.SyntaxTree.fromFile(path, self.source_manager, options)
                self._trees.append(tree)
                self.compilation.addSyntaxTree(tree)

            self._collect_diagnostics()
            return not self.reporter.has_errors()
        except Exception as e:  # pragma: no cover - defensive
            self.reporter.error(f"parser error: {e}")
            return False

    def parse_text(self, text: str, name: str = "<source>") -> bool:
        """Parse a string of SystemVerilog (no library, for unit tests).

        Threads ``config`` defines/incdirs through the preprocessor so
        ``+define+`` behaves the same as for file parsing.
        """
        try:
            incdirs = list(self.config.incdirs)
            self.source_manager = self._make_source_manager(incdirs)
            options = self._make_options(incdirs)
            self.compilation = ast.Compilation()
            tree = syntax.SyntaxTree.fromText(text, self.source_manager, name, "", options)
            self._trees = [tree]
            self.compilation.addSyntaxTree(tree)
            self._collect_diagnostics()
            return not self.reporter.has_errors()
        except Exception as e:  # pragma: no cover - defensive
            self.reporter.error(f"parser error: {e}")
            return False

    # -- access ----------------------------------------------------------
    def get_root(self):
        return self.compilation.getRoot() if self.compilation else None

    # -- internals -------------------------------------------------------
    def _collect_diagnostics(self) -> None:
        assert self.compilation is not None
        engine = pyslang.DiagnosticEngine(self.source_manager)
        for diag in self.compilation.getAllDiagnostics():
            text = engine.reportAll(self.source_manager, [diag]).strip()
            if diag.isError():
                self.reporter.error(text)
            # Warnings from library elaboration are noisy; record nothing for now.
