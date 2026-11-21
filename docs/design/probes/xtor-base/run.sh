#!/bin/sh
# Builds and runs xtor_base.sv against rt-sv and std with Verilator; the
# output should match expected.txt. Run from the workspace root through
# direnv: direnv exec . sh docs/design/probes/xtor-base/run.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
P=${P:-$(cd "$HERE/../../../../packages" && pwd)}
OUT=${OUT:-$HERE/build}
mkdir -p "$OUT/obj"
verilator --binary -Wno-fatal -Wno-lint -Wno-style --top-module xtor_base \
    -Mdir "$OUT/obj" -o Vx \
    -I"$P/fw-hdl-rt-sv/sv" -I"$P/fw-hdl-spec/bindings/sv" -I"$P/fw-hdl-spec/std" \
    "$P/fw-hdl-rt-sv/sv/fw_hdl_pkg.sv" "$P/fw-hdl-spec/std/fw_hdl_std_pkg.sv" \
    "$HERE/xtor_base.sv" > "$OUT/build.log" 2>&1
"$OUT/obj/Vx" > "$OUT/run.log" 2>&1
grep -v '^- ' "$OUT/run.log"
