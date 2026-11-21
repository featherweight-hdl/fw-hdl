#!/bin/sh
# Synthesis figures per variant x W (N = 4, DEPTH = 2): yosys `synth`
# (generic gates), flattened: cells, flop bits, and logic levels on the
# longest path (`ltp -noff`: gates between flops/ports). The modules are
# parameterized with `parameter type`, so each is read through sv2v under a
# wrapper that fixes TI/TP/TM for W. Logs in rundir/measure/; one line per
# point in rundir/measure/measure.txt. Run from examples/rr_merge_pipe:
#   direnv exec . sh scripts/measure.sh [variants...]
set -e
out=rundir/measure
mkdir -p $out
VARIANTS=${*:-"rr_merge_pipe rr_merge_pipe_stall1 rr_merge_pipe_stall2 rr_merge_pipe_elastic1
                rr_merge_pipe_elastic2 rr_merge_pipe_credit1 rr_merge_pipe_credit2
                rr_merge_pipe_skid rr_merge_pipe_out1"}
sum=$out/measure.txt
: > $sum
for v in $VARIANTS; do
    for w in 8 16 32; do
        tag=${v}_w$w
        tp=""
        [ $v != rr_merge_pipe ] && tp=".TP(pipe_types_pkg::pipe_prod${w}_t), "
        cat > $out/$tag.top.sv <<EOT
module meas_top (
    input  logic clock, reset,
    input  logic [3:0] in_valid, output logic [3:0] in_ready,
    input  pipe_types_pkg::pipe_in${w}_t [3:0] in_data,
    output logic out_valid, input logic out_ready,
    output pipe_types_pkg::pipe_mid${w}_t out_data);
    $v #(.TI(pipe_types_pkg::pipe_in${w}_t), ${tp}.TM(pipe_types_pkg::pipe_mid${w}_t),
         .N(4), .DEPTH(2)) dut (.*);
endmodule
EOT
        sv2v src/pipe_types_pkg.sv rtl/gen/$v.sv $out/$tag.top.sv > $out/$tag.v
        yosys -q -l $out/$tag.log -p "read_verilog $out/$tag.v; hierarchy -top meas_top; \
            synth -flatten -top meas_top; tee -q -o $out/$tag.stat stat; \
            tee -q -o $out/$tag.ltp ltp -noff" > /dev/null
        cells=$(grep -E '^ +[0-9]+ cells$' $out/$tag.stat | tail -1 | awk '{print $1}')
        flops=$(grep -E '\$_.*DFF' $out/$tag.stat | awk '{s+=$1} END {print s+0}')
        lev=$(grep -o 'length=[0-9]*' $out/$tag.ltp | head -1 | cut -d= -f2)
        printf '%-24s W=%-2s cells=%-6s flops=%-5s levels=%s\n' $v $w $cells $flops $lev | tee -a $sum
    done
done
