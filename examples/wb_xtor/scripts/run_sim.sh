#!/bin/sh
# Builds the bench under Verilator on fw-hdl-rt-sv and fw-hdl-spec, and runs
# it plain, with +rand, and with each mutant (which must fail). Run from the
# example directory under direnv; output under $OUT (default rundir/).
set -e
ex=$(cd "$(dirname "$0")/.." && pwd)
pk=${IVPM_PACKAGES:?run under direnv}
rt=$pk/fw-hdl-rt-sv/sv
sp=$pk/fw-hdl-spec
out=${OUT:-$ex/rundir}
mkdir -p "$out"

verilator --binary -Wno-fatal -Wno-lint -Wno-style \
    --top-module wb_xtor_tb -Mdir "$out/obj" -o Vwb_xtor_tb \
    -I"$rt" -I"$sp/bindings/sv" -I"$sp/std" -I"$ex/src" \
    "$rt/fw_hdl_pkg.sv" "$sp/std/fw_hdl_std_pkg.sv" \
    "$ex/src/wb_api_pkg.sv" "$ex/src/wb_pkg.sv" "$ex/tb/wb_xtor_tb.sv" "$ex/tb/wb_xtor_tb_top.sv" > "$out/build.log" 2>&1 \
    || { tail -40 "$out/build.log"; exit 1; }

for a in "" +rand +mut_init +mut_tgt; do
    echo "== ${a:-plain}"
    "$out/obj/Vwb_xtor_tb" +fw_edges=400 $a | grep -E '^(R|D) '
done
