"""fw.hdl — Featherweight-HDL front end and synthesis flow.

Pipeline (see ``DESIGN.md`` / ``PLAN.md`` alongside this package):

    FW-SystemVerilog --sv2ir--> SPL IR --spl2rtl--> RTL IR --rtl2v--> Verilog

All three levels are :mod:`zuspec.ir.core` IR.  ``fw.hdl.fe`` is the
SystemVerilog front end (sv2ir); ``fw.hdl.lower`` lowers SPL IR to RTL IR
(spl2rtl); ``fw.hdl.emit`` renders RTL IR to Verilog via ``zuspec.be.sv``
(rtl2v).  The ``synth`` flow chains all three.
"""

__version__ = "0.0.1"
