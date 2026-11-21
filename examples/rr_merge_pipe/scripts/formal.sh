#!/bin/sh
# F7: SBY proofs on the generated stall maps (scripts/gen_auto.py 1 2 3):
#   datapath K   (formal/fv_props_datapath.v): == f delayed by K, sink ready, W = 8;
#   ctrl K       (formal/fv_props_ctrl.v): order/loss/dup/content, occupancy,
#                throughput, out protocol; 2-bit payload;
# and mutants that must FAIL: datapath with the wrong shift (K - 1); ctrl on
# a controller whose in.ready ignores the stage (always 1). The typed DUT
# wrapper (formal/fv_wrap.sv) goes through sv2v; the properties don't (sv2v
# drops assertions). Logs and SBY
# directories in rundir/formal/. Run from examples/rr_merge_pipe:
#   direnv exec . sh scripts/formal.sh [K ...]
out=rundir/formal
mkdir -p $out
fail=0
run() {   # <name> <props> <module> <K> <shift> <gen file> <ti> <tm> <wi> <wm> <engine> <depth> <expect>
    name=$1; props=$2; mod=$3; k=$4; sh=$5; gen=$6; ti=$7; tm=$8; wi=$9; shift 9
    wm=$1; eng=$2; depth=$3; expect=$4
    sed "s/@MOD@/$mod/g; s/@TI@/$ti/g; s/@TM@/$tm/g" formal/fv_wrap.sv > $out/$name.wrap.sv
    sv2v src/pipe_types_pkg.sv formal/fv_types.sv $gen $out/$name.wrap.sv > $out/$name.wrap.v \
        2> $out/$name.sv2v.log || { echo "$name: sv2v FAILED"; fail=1; return; }
    sed "s/@K@/$k/g; s/@SHIFT@/$sh/g; s/@WI@/$wi/g; s/@WM@/$wm/g" $props > $out/$name.props.v
    cat > $out/$name.sby <<EOT
[options]
mode prove
aigsmt boolector
depth $depth

[engines]
$eng

[script]
read_verilog $name.wrap.v
read_verilog -formal $name.props.v
prep -top fv_top

[files]
$name.wrap.v
$name.props.v
EOT
    (cd $out && sby -f $name.sby > $name.log 2>&1)
    if grep -q "DONE (PASS" $out/$name.log; then r=PASS
    elif grep -q "DONE (FAIL" $out/$name.log; then r=FAIL
    else r=ERROR; fi
    if [ $r = $expect ]; then echo "$name: $r (expected)"; else
        echo "$name: $r, expected $expect, see $out/$name.log"; fail=1; fi
}
W8="pipe_types_pkg::pipe_in8_t pipe_types_pkg::pipe_mid8_t 33 25"
W2="fv_types_pkg::fv_in_t fv_types_pkg::fv_mid_t 6 5"
for k in ${*:-1 2 3}; do
    gen=rtl/gen/rr_merge_pipe_auto$k.sv
    mod=pipe_map_in_stall$k
    run datapath_k$k formal/fv_props_datapath.v $mod $k $k $gen $W8 "smtbmc boolector" $((k + 3)) PASS
    run datapath_k${k}_mut_shift formal/fv_props_datapath.v $mod $k $((k - 1)) $gen $W8 \
        "smtbmc boolector" $((k + 3)) FAIL
    run ctrl_k$k formal/fv_props_ctrl.v $mod $k 0 $gen $W2 "abc pdr" 30 PASS
    sed "s/in_ready\[i\] = !s${k}_v\[i\] || out_ready\[i\];/in_ready[i] = 1'b1;/" $gen \
        > $out/mut_ready_k$k.sv
    run ctrl_k${k}_mut_ready formal/fv_props_ctrl.v $mod $k 0 $out/mut_ready_k$k.sv $W2 \
        "abc pdr" 30 FAIL
done
exit $fail
