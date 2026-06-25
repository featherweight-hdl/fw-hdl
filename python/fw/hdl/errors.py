"""Diagnostics for the fw-hdl flow.

A small, dependency-free error/warning collector used by every stage (parser,
mappers, lowering).  Mirrors the shape of ``zuspec.fe.sv.error`` so behaviour is
familiar, but is our own code.
"""
from __future__ import annotations

import dataclasses as dc
import enum
from typing import List, Optional


class Severity(enum.Enum):
    WARNING = enum.auto()
    ERROR = enum.auto()


@dc.dataclass
class Diagnostic:
    """A single diagnostic with optional source location."""

    severity: Severity
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    suggestion: Optional[str] = None

    def __str__(self) -> str:
        sev = "error" if self.severity is Severity.ERROR else "warning"
        loc = ""
        if self.file:
            loc = self.file
            if self.line is not None:
                loc += f":{self.line}"
                if self.column is not None:
                    loc += f":{self.column}"
            loc += ": "
        msg = f"{loc}{sev}: {self.message}"
        if self.suggestion:
            msg += f"\n  help: {self.suggestion}"
        return msg


class FwHdlError(Exception):
    """Raised when an unsupported/unrecognized construct is encountered.

    ``sv2ir`` is strict: rather than silently dropping constructs it can't map,
    it raises this so gaps surface instead of miscompiling (PLAN.md §2 / DESIGN
    §6).  The attached :class:`Diagnostic` carries the location.
    """

    def __init__(self, diagnostic: Diagnostic):
        super().__init__(str(diagnostic))
        self.diagnostic = diagnostic


class ErrorReporter:
    """Collects diagnostics and renders a report."""

    def __init__(self) -> None:
        self.diagnostics: List[Diagnostic] = []

    # -- recording -------------------------------------------------------
    def error(
        self,
        message: str,
        *,
        file: Optional[str] = None,
        line: Optional[int] = None,
        column: Optional[int] = None,
        suggestion: Optional[str] = None,
    ) -> Diagnostic:
        d = Diagnostic(Severity.ERROR, message, file, line, column, suggestion)
        self.diagnostics.append(d)
        return d

    def warning(
        self,
        message: str,
        *,
        file: Optional[str] = None,
        line: Optional[int] = None,
        column: Optional[int] = None,
        suggestion: Optional[str] = None,
    ) -> Diagnostic:
        d = Diagnostic(Severity.WARNING, message, file, line, column, suggestion)
        self.diagnostics.append(d)
        return d

    def fail(self, message: str, **kwargs) -> "FwHdlError":
        """Record an error and return an :class:`FwHdlError` to raise.

        Usage: ``raise reporter.fail("unsupported statement", file=..., line=...)``.
        """
        return FwHdlError(self.error(message, **kwargs))

    # -- querying --------------------------------------------------------
    def has_errors(self) -> bool:
        return any(d.severity is Severity.ERROR for d in self.diagnostics)

    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity is Severity.ERROR]

    def warnings(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.severity is Severity.WARNING]

    def clear(self) -> None:
        self.diagnostics.clear()

    def report(self) -> str:
        if not self.diagnostics:
            return "no diagnostics"
        return "\n".join(str(d) for d in self.diagnostics)
