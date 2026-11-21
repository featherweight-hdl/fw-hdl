#!/bin/sh
# Builds and runs edge_phase.sv against this repo's src/ with Verilator.
# Run from the repo root: direnv exec . sh docs/design/probes/sync-domains-x0/run_edge_phase.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
S=${S:-$(cd "$HERE/../../../../src" && pwd)}
OUT=${OUT:-$HERE/build/edge_phase}
mkdir -p "$OUT/obj"
verilator --binary --timing -Wno-fatal -Wno-lint -Wno-style --top-module edge_phase \
    -Mdir "$OUT/obj" -o Vx -I"$S" \
    "$S/fw_clock_xtor_if.sv" "$S/fw_clock_period_xtor_if.sv" "$S/fw_hdl_pkg.sv" \
    "$S/fw_clock_period_xtor.sv" "$HERE/edge_phase.sv" > "$OUT/build.log" 2>&1
"$OUT/obj/Vx" > "$OUT/run.log" 2>&1
grep -v '^- ' "$OUT/run.log" | sort -t@ -k2 -n
