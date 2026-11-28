"""Lowers wb_initiator #(32, 32) to RTL with fw-hdl-fe-sv (tb/wb_emit.sv):
module wb_dut (its pins and its crossings' ready/valid ports) over
wb_initiator_rtl (renamed: the class wb_initiator is compiled with it in
the mixed bench). Usage: emit_rtl.py <out dir>; prints the filelist."""
import sys
from pathlib import Path

from fw.hdl.fe.sv import elaborate
from fw.hdl.fe.sv.emit import emit_sv

ex = Path(__file__).resolve().parents[1]
r = elaborate([str(ex / "src" / "wb_api_pkg.sv"), str(ex / "src" / "wb_pkg.sv"), str(ex / "tb" / "wb_emit.sv")],
              top="wb_emit_pkg::top", incdirs=[str(ex / "src")], lower=True)
if not r.ok:
    sys.exit("\n".join(map(str, r.diags)))
ctxt, top = r.to_ir()
for d in r.ir_diags:
    print(d, file=sys.stderr)
res = emit_sv(ctxt, top, sys.argv[1], top_module="wb_dut",
              rename={"wb_initiator": "wb_initiator_rtl"})
print(res.filelist)
