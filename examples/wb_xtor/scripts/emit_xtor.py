"""T3/T4 (docs/design/xtor-shell-plan.md): emits wb_initiator #(32, 32)
(tb/wb_emit.sv) or wb_target #(32, 32) (tb/wb_emit_tgt.sv) as a
transactor shell: core <xtor>_xtor_core, types package
<xtor>_xtor_types_pkg, interface <xtor>_xtor_if, shell <xtor>_xtor and
bridge class <xtor>_bridge (<xtor>_bridge_pkg.sv, not in the filelist),
generated from the IR (fw.hdl.fe.sv.emit.emit_xtor).
Usage: emit_xtor.py <init|tgt> <out dir> [fw-hdl|plain|cocotb|cocotb-edge];
prints the filelist. The last argument is the bridge's flavor (D10, T4c,
T7; default fw-hdl); cocotb-edge is the cocotb bridge that samples at every
edge instead of waiting on ready/valid."""
import sys
from pathlib import Path

from fw.hdl.fe.sv import elaborate
from fw.hdl.fe.sv.emit import emit_xtor

XTOR = {  # which: (class, emit top file, emit top)
    "init": ("wb_initiator", "wb_emit.sv", "wb_emit_pkg::top"),
    "tgt":  ("wb_target", "wb_emit_tgt.sv", "wb_emit_tgt_pkg::top"),
}
cls, src, tname = XTOR[sys.argv[1]]
ex = Path(__file__).resolve().parents[1]
r = elaborate([str(ex / "src" / "wb_api_pkg.sv"), str(ex / "src" / "wb_pkg.sv"), str(ex / "tb" / src)],
              top=tname, incdirs=[str(ex / "src")], lower=True)
if not r.ok:
    sys.exit("\n".join(map(str, r.diags)))
ctxt, top = r.to_ir()
flavor = sys.argv[3] if len(sys.argv) > 3 else "fw-hdl"
wait = "edge" if flavor == "cocotb-edge" else "event"
print(emit_xtor(ctxt, top, cls, sys.argv[2], flavor=flavor.split("-edge")[0],
                cocotb_wait=wait).filelist)
