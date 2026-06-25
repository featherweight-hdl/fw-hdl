"""Flow configuration shared by every fw-hdl stage."""
from __future__ import annotations

import dataclasses as dc
from typing import Dict, List, Optional


@dc.dataclass
class FlowConfig:
    """Configuration for an fw-hdl run.

    Attributes
    ----------
    incdirs:
        Include search paths (from ``+incdir+`` / ``-I``).  The fw-hdl library
        directories are added automatically by the parser.
    defines:
        Preprocessor macros (from ``+define+`` / ``-D``); ``name -> value`` where
        a valueless ``+define+FOO`` maps to ``"FOO" -> ""``.
    top:
        Name of the root component *class* to synthesize (e.g. ``blinky``).
    top_module:
        Name of the ``*_top`` module carrying the ``fw_root`` binding, used to
        elaborate the class->module boundary (DESIGN §3).
    reset_style:
        One of ``async_high`` (default — the fw-hdl std, active-high),
        ``sync_high``, ``sync_low``, ``async_low``.  (be-sv currently emits a
        synchronous sensitivity list regardless; the polarity is what matters.)
    output:
        Output file or directory.
    dump_ir:
        Emit intermediate IR for inspection.
    """

    incdirs: List[str] = dc.field(default_factory=list)
    defines: Dict[str, str] = dc.field(default_factory=dict)
    top: Optional[str] = None
    top_module: Optional[str] = None
    reset_style: str = "async_high"
    output: Optional[str] = None
    dump_ir: bool = False

    def predefine_strings(self) -> List[str]:
        """Render ``defines`` as slang ``predefines`` entries (``NAME=VALUE``)."""
        out = []
        for name, value in self.defines.items():
            out.append(f"{name}={value}" if value != "" else name)
        return out
