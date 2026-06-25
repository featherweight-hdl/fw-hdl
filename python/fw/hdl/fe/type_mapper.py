"""Map SystemVerilog data types to :class:`zuspec.ir.core.DataTypeInt`.

Policy (DESIGN §2.2 / PLAN §1.2):
  - integral 2-state types map directly to ``DataTypeInt(bits, signed)``;
  - 4-state types (``logic``/``reg``) are normally unsupported for synthesis,
    **except** a 1-bit ``logic`` pin type (the blinky LED ``led_t``) — pin nets
    are conventionally ``logic``.  Wider 4-state on a synthesizable signal is a
    hard error so the gap surfaces rather than miscompiling.
"""
from __future__ import annotations

from typing import Optional

import zuspec.ir.core as ir

from ..config import FlowConfig
from ..errors import ErrorReporter


class TypeMapper:
    def __init__(self, config: FlowConfig, reporter: ErrorReporter):
        self.config = config
        self.reporter = reporter

    def map_type(self, sv_type, *, what: str = "value") -> Optional[ir.DataTypeInt]:
        """Map an integral SV type.  Returns ``None`` (and records an error) for
        an unsupported type."""
        if not getattr(sv_type, "isIntegral", False):
            self.reporter.error(
                f"unsupported non-integral type for {what}: {sv_type}"
            )
            return None

        bits = int(sv_type.bitWidth)
        signed = bool(getattr(sv_type, "isSigned", False))
        four_state = bool(getattr(sv_type, "isFourState", False))

        if four_state and bits != 1:
            self.reporter.error(
                f"4-state type ({sv_type}) is not synthesizable for {what}; "
                f"use a 2-state type",
                suggestion="bit/int/logic[0:0] (1-bit logic pins are allowed)",
            )
            return None

        return ir.DataTypeInt(bits=bits, signed=signed)
