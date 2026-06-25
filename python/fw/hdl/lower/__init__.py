"""fw.hdl.lower — spl2rtl: lower bound SPL IR to RTL-level IR.

Sequences the ``forever`` loop's awaited beats (``put``/``tick``) into an FSM
expressed as clocked ``sync_processes`` (state register + tick counter +
registered outputs), all in :mod:`zuspec.ir.core` so the ``be-sv`` emitter
renders it directly (DESIGN §9.1, settled by spike).
"""
