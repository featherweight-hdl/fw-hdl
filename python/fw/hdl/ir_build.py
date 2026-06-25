"""IR builder helpers — re-exported from the shared lowering library.

These generic ``zuspec.ir.core`` constructors now live in
``zuspec.synth.spl.builders`` so the centralized lowering and the fw-hdl front
end share one set of helpers (and one RTL-contract chokepoint).  This module is a
thin re-export to preserve the ``fw.hdl.ir_build`` import path.
"""
from zuspec.synth.spl.builders import (  # noqa: F401
    int_t,
    in_port,
    out_reg,
    reg,
    sref,
    const,
    binop,
    add,
    cmp,
    cmp_eq,
    inv,
    lognot,
    assign,
    if_,
    sync_proc,
    component,
    context,
    field_index,
    validate_rtl_component,
)
