"""fw.hdl.fe.bind — the class->module boundary (DESIGN §3).

Elaborates the ``fw_root`` binding in a ``*_top`` module so the abstract class
ports/clock-domain become concrete module pins (clock/reset/<pin>) and the
``put``/``tick`` beats gain hardware meaning.
"""
