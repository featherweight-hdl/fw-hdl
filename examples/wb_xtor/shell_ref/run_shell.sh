#!/bin/sh
# T0/T5 (docs/design/xtor-shell-plan.md): run_shell.sh [init|tgt]. Emits
# the transactor's core, builds the hand-written shell, interface and
# bridge with the class bench (wb_xtor_shell_<which>.sv) and runs it plain,
# +rand and with the other transactor's mutant (+mut_tgt for init,
# +mut_init for tgt), which must fail. Run from examples/wb_xtor under
# direnv; output under $OUT (default rundir/shell_<which>). GEN=1 (T3, T4):
# the interface, shell and bridge generated from the IR
# (scripts/emit_xtor.py) instead of the hand-written ones (output default
# rundir/gen_<which>).
set -e
w=${1:-init}
case $w in
    init) x=wb_initiator; mut=+mut_tgt ;;
    tgt)  x=wb_target;    mut=+mut_init ;;
    *)    echo "usage: $0 [init|tgt]" >&2; exit 2 ;;
esac
ex=$(cd "$(dirname "$0")/.." && pwd)
sr=$ex/shell_ref
pk=${IVPM_PACKAGES:?run under direnv}
rt=$pk/fw-hdl-rt-sv/sv
sp=$pk/fw-hdl-spec
top=wb_xtor_shell_$w
if [ -n "$GEN" ]; then
    out=${OUT:-$ex/rundir/gen_$w}
    mkdir -p "$out"
    fl=$(python "$ex/scripts/emit_xtor.py" "$w" "$out/gen" 2> "$out/emit.log") \
        || { tail -40 "$out/emit.log"; exit 1; }
    hand=""
    bridge="-I$out/gen $out/gen/${x}_bridge_pkg.sv"
    def=+define+GEN_SHELL
else
    out=${OUT:-$ex/rundir/shell_$w}
    mkdir -p "$out"
    fl=$(python "$sr/emit_core.py" "$w" "$out/gen" 2> "$out/emit.log") \
        || { tail -40 "$out/emit.log"; exit 1; }
    hand="$sr/${x}_xtor_if.sv $sr/${x}_xtor.sv"
    bridge="$sr/${x}_bridge_pkg.sv"
    def=
fi

verilator --binary -Wno-fatal -Wno-lint -Wno-style \
    --top-module $top $def -Mdir "$out/obj" -o V$top \
    -I"$rt" -I"$sp/bindings/sv" -I"$sp/std" -I"$ex/src" \
    "$rt/fw_hdl_pkg.sv" "$sp/std/fw_hdl_std_pkg.sv" "$rt/fw_pin_bridge.sv" \
    $(cat "$fl") $hand \
    "$ex/src/wb_api_pkg.sv" "$ex/src/wb_pkg.sv" "$ex/tb/wb_xtor_tb.sv" $bridge \
    "$sr/$top.sv" > "$out/build.log" 2>&1 \
    || { tail -40 "$out/build.log"; exit 1; }

for a in "" +rand $mut; do
    echo "== ${a:-plain}"
    "$out/obj/V$top" $a | grep -E '^(R|D) '
done
