"""spl2rtl — fw-hdl adapter over the centralized lowering.

The transparent SPL→RTL lowering now lives in ``zuspec.synth.spl`` (shared across
front ends).  This module adapts fw-hdl's ``FlowConfig`` / ``ErrorReporter``
calling convention to it, so existing fw-hdl callers and tests are unchanged.
"""
from __future__ import annotations

from typing import Optional

import zuspec.ir.core as ir
from zuspec.synth.spl import (
    SplConfig,
    SplLowerError,
    lower_component as _lower_component,
    lower_context as _lower_context,
)

from ..config import FlowConfig
from ..errors import ErrorReporter


def _cfg(config: FlowConfig) -> SplConfig:
    return SplConfig(reset_style=config.reset_style)


def lower_context(spl_ctxt: ir.Context, config: FlowConfig,
                  reporter: ErrorReporter) -> Optional[ir.Context]:
    try:
        return _lower_context(spl_ctxt, _cfg(config))
    except SplLowerError as e:
        reporter.error(str(e))
        return None


def lower_component(spl: ir.DataTypeComponent, config: FlowConfig,
                    reporter: ErrorReporter) -> Optional[ir.DataTypeComponent]:
    try:
        return _lower_component(spl, _cfg(config))
    except SplLowerError as e:
        reporter.error(str(e))
        return None
