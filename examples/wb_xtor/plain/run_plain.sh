#!/bin/sh
# T4c (docs/design/xtor-shell-plan.md, D10): emits wb_initiator and
# wb_target as shells with plain bridges (scripts/emit_xtor.py ... plain),
# builds wb_plain_tb.sv with no fw-hdl package on the command line, and
# runs it plain, +rand, +mut_mem (must fail) and +no_set (must stop with
# $fatal). Run from examples/wb_xtor under direnv; output under $OUT
# (default rundir/plain).
set -e
ex=$(cd "$(dirname "$0")/.." && pwd)
pl=$ex/plain
out=${OUT:-$ex/rundir/plain}
mkdir -p "$out"
fls=""
for w in init tgt; do
    fl=$(python "$ex/scripts/emit_xtor.py" "$w" "$out/gen_$w" plain 2> "$out/emit_$w.log") \
        || { tail -40 "$out/emit_$w.log"; exit 1; }
    fls="$fls $(grep -v -e '_lowered\.sv$' "$fl")"
done

verilator --binary -Wno-fatal -Wno-lint -Wno-style \
    --top-module wb_plain_tb -Mdir "$out/obj" -o Vwb_plain_tb \
    -I"$ex/src" -I"$pl" -I"$out/gen_init" -I"$out/gen_tgt" \
    "$ex/src/wb_api_pkg.sv" $fls \
    "$out/gen_init/wb_initiator_bridge_pkg.sv" "$out/gen_tgt/wb_target_bridge_pkg.sv" \
    "$pl/wb_plain_clk_if.sv" "$pl/wb_plain_tb_pkg.sv" "$pl/wb_plain_tb.sv" \
    > "$out/build.log" 2>&1 \
    || { tail -40 "$out/build.log"; exit 1; }

for a in "" +rand +mut_mem +no_set; do
    echo "== ${a:-plain}"
    "$out/obj/Vwb_plain_tb" $a 2>&1 | grep -E '^(R |%Fatal|.*\$fatal|.*run\(\) with)' || true
done
