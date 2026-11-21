#!/bin/sh
# F6 exit: the generated rr_merge_pipe_auto1 (scripts/gen_auto.py) against
# the hand-written rr_merge_pipe_stall1, unbounded (yosys/equiv_pair.ys), at
# W = 8, 16, 32 (N = 4). Logs in rundir/equiv/. Run from examples/rr_merge_pipe:
#   direnv exec . sh scripts/equiv_auto.sh [gold gate]
gold=${1:-rr_merge_pipe_stall1}; gate=${2:-rr_merge_pipe_auto1}
out=rundir/equiv
mkdir -p $out
wrap() {    # <module> <W> -> $out/<module>_w<W>.v
    m=$1; w=$2
    tp=""
    awk "/^module $m /,/\\)/" rtl/gen/$m.sv | grep -q "parameter type TP" \
        && tp=".TP(pipe_types_pkg::pipe_prod${w}_t), "
    cat > $out/${m}_w$w.top.sv <<EOT
module meas_top (
    input  logic clock, reset,
    input  logic [3:0] in_valid, output logic [3:0] in_ready,
    input  pipe_types_pkg::pipe_in${w}_t [3:0] in_data,
    output logic out_valid, input logic out_ready,
    output pipe_types_pkg::pipe_mid${w}_t out_data);
    $m #(.TI(pipe_types_pkg::pipe_in${w}_t), ${tp}.TM(pipe_types_pkg::pipe_mid${w}_t),
         .N(4), .DEPTH(2)) dut (.*);
endmodule
EOT
    sv2v src/pipe_types_pkg.sv rtl/gen/$m.sv $out/${m}_w$w.top.sv > $out/${m}_w$w.v
}
fail=0
for w in 8 16 32; do
    wrap $gold $w; wrap $gate $w
    sed "s|@GOLD@|$out/${gold}_w$w.v|; s|@GATE@|$out/${gate}_w$w.v|" yosys/equiv_pair.ys \
        > $out/${gate}_w$w.ys
    if yosys -q -l $out/${gate}_w$w.log $out/${gate}_w$w.ys > /dev/null 2>&1; then
        echo "equiv $gate = $gold W=$w: proven (unbounded)"
    else
        echo "equiv $gate = $gold W=$w: NOT proven, see $out/${gate}_w$w.log"; fail=1
    fi
done
exit $fail
