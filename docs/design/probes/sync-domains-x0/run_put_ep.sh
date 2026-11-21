#!/bin/sh
# Builds put_ep.sv against an X0 kernel (S=<src with the X0 kernel>) and runs
# it with the task before and after the kernel at each edge. The two logs
# must match. Run from the repo root:
#   S=<mirror>/src direnv exec . sh docs/design/probes/sync-domains-x0/run_put_ep.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
# DEFS=+define+NAIVE builds the negative control (expect DIFFER).
S=${S:?set S to a src/ with the X0 kernel}
OUT=${OUT:-$HERE/build/put_ep}
mkdir -p "$OUT/obj"
verilator ${DEFS} --binary --timing -Wno-fatal -Wno-lint -Wno-style --top-module put_ep_probe \
    -Mdir "$OUT/obj" -o Vx -I"$S" \
    "$S/fw_clock_xtor_if.sv" "$S/fw_clock_period_xtor_if.sv" "$S/fw_hdl_pkg.sv" \
    "$HERE/put_ep.sv" > "$OUT/build.log" 2>&1
for kf in 0 1; do "$OUT/obj/Vx" +kfirst=$kf > "$OUT/run_kfirst$kf.log" 2>&1; done
grep -h '^X0.4' "$OUT"/run_kfirst*.log
a=$(grep '^X0.4' "$OUT/run_kfirst0.log" | sed 's/kfirst=[01] //'); b=$(grep '^X0.4' "$OUT/run_kfirst1.log" | sed 's/kfirst=[01] //')
[ -n "$a" ] && [ "$a" = "$b" ] && echo "SAME in both orders" || echo "DIFFER"
