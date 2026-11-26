"""T0/T5: lowers wb_initiator #(32, 32) (tb/wb_emit.sv) or wb_target
#(32, 32) (tb/wb_emit_tgt.sv) and names its module <xtor>_xtor_core, as
the shell expects (D1). The emitted top (<xtor>_xtor_lowered) is unused;
its types package (<xtor>_xtor_lowered_types_pkg) is the interface's too.
Usage: emit_core.py <init|tgt> <out dir>; prints the filelist."""
import sys
from pathlib import Path

from fw.hdl.fe.sv import elaborate
from fw.hdl.fe.sv.emit import emit_sv

XTOR = {  # which: (class, emit top file, emit top)
    "init": ("wb_initiator", "wb_emit.sv", "wb_emit_pkg::top"),
    "tgt":  ("wb_target", "wb_emit_tgt.sv", "wb_emit_tgt_pkg::top"),
}
cls, src, tname = XTOR[sys.argv[1]]
ex = Path(__file__).resolve().parents[1]
r = elaborate([str(ex / "src" / "wb_api_pkg.sv"), str(ex / "src" / "wb_pkg.sv"), str(ex / "tb" / src)],
              top=tname, incdirs=[str(ex / "src")])
if not r.ok:
    sys.exit("\n".join(map(str, r.diags)))
ctxt, top = r.to_ir()
res = emit_sv(ctxt, top, sys.argv[2], top_module=f"{cls}_xtor_lowered",
              rename={cls: f"{cls}_xtor_core"})
print(res.filelist)
