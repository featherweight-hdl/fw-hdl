#!/bin/sh
# Lowers wb_initiator to RTL (scripts/emit_rtl.py) and runs it in the mixed
# bench (tb/wb_xtor_mixed.sv): plain, with +rand, and with the target
# mutant (which must fail). Run from the example directory under direnv;
# output under $OUT (default rundir/mixed).
set -e
ex=$(cd "$(dirname "$0")/.." && pwd)
pk=${IVPM_PACKAGES:?run under direnv}
rt=$pk/fw-hdl-rt-sv/sv
sp=$pk/fw-hdl-spec
out=${OUT:-$ex/rundir/mixed}
mkdir -p "$out"

fl=$(python "$ex/scripts/emit_rtl.py" "$out/gen" 2> "$out/emit.log") \
    || { tail -40 "$out/emit.log"; exit 1; }

verilator --binary -Wno-fatal -Wno-lint -Wno-style \
    --top-module wb_xtor_mixed -Mdir "$out/obj" -o Vwb_xtor_mixed \
    -I"$rt" -I"$sp/bindings/sv" -I"$sp/std" -I"$ex/src" \
    "$rt/fw_hdl_pkg.sv" "$sp/std/fw_hdl_std_pkg.sv" "$rt/fw_pin_bridge.sv" \
    "$ex/src/wb_api_pkg.sv" "$ex/src/wb_pkg.sv" "$ex/tb/wb_xtor_tb.sv" $(cat "$fl") \
    "$ex/tb/wb_xtor_mixed.sv" > "$out/build.log" 2>&1 \
    || { tail -40 "$out/build.log"; exit 1; }

for a in "" +rand +mut_tgt; do
    echo "== ${a:-plain}"
    "$out/obj/Vwb_xtor_mixed" $a | grep -E '^(R|D) '
done
