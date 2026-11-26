"""Elaborates the bench's top with fw-hdl-fe-sv (the static front end) and
prints its diagnostics, protocol table and API bindings as JSON. Stops
before the IR mapping, which is for emission and rejects task code. Run from
the example directory under direnv."""
import json
import os
import sys

from fw.hdl.fe.sv.elab import elaborate

ex = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
r = elaborate([os.path.join(ex, "src", "wb_api_pkg.sv"), os.path.join(ex, "src", "wb_pkg.sv"), os.path.join(ex, "tb", "wb_xtor_tb.sv")],
              "wb_xtor_tb_pkg::top_c")
nl = r.netlist()
json.dump({"ok": r.ok, "diags": [str(d) for d in r.diags],
           "protocols": nl.get("protocols"), "bindings": nl.get("bindings")},
          sys.stdout, indent=1, sort_keys=True)
print()
sys.exit(0 if r.ok else 1)
