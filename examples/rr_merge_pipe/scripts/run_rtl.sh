#!/bin/sh
# Build and run pipe_rtl_tb on a module from rtl/gen, one build
# per <module, W, N>, then the given seeds x sink modes. Logs go to
# rundir/rtl/<tag>/. Run from examples/rr_merge_pipe:
#   direnv exec . sh scripts/run_rtl.sh <rtl file> <module> [W] [N] [seeds] [sinks] [extra plusargs]
# Prints one line per run and exits 1 if any run fails.
set -e
src=$1; mod=$2; w=${3:-8}; n=${4:-4}; seeds=${5:-"1 2 3"}; sinks=${6:-"0 1 2"}; extra=$7
tag=${mod}_w${w}_n${n}
out=rundir/rtl/$tag
mkdir -p $out
defs="+define+PIPE_DUT=$mod +define+PIPE_N=$n"
[ "$w" != 8 ] && defs="$defs +define+PIPE_W_$w"
awk "/^module $mod /,/\\)/" $src | grep -q "parameter type TP" && defs="$defs +define+PIPE_TP"
verilator --binary -j 0 --timing -Wno-fatal -Wno-lint -Wno-style $defs \
    --top-module pipe_rtl_tb -Mdir $out/obj src/pipe_types_pkg.sv $src \
    tb/pipe_bench.sv tb/pipe_mutant.sv tb/pipe_rtl_tb.sv > $out/build.log 2>&1 \
    || { echo "$tag: BUILD FAILED, see $out/build.log"; exit 1; }
fail=0
for s in $seeds; do
    for k in $sinks; do
        log=$out/run_s${s}_k${k}.log
        if $out/obj/Vpipe_rtl_tb +verilator+seed+$s +sink=$k $extra > $log 2>&1 \
                && grep -q '^PASS' $log; then
            echo "$tag seed=$s sink=$k: $(grep -h '^throughput\|^latency' $log | tr '\n' ' ')PASS"
        else
            echo "$tag seed=$s sink=$k: FAIL, see $log"; fail=1
        fi
    done
done
exit $fail
