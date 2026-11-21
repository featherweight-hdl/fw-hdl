#!/bin/sh
# Every variant on pipe_bench: W = 8, N = 4 with 20 seeds x 3 sink modes;
# W = 16, 32 (N = 4) and N = 2 (W = 8) with 3 seeds x 3 sink modes. One
# line per configuration in rundir/rtl/matrix.txt. Run from
# examples/rr_merge_pipe after scripts/gen_rtl.py:
#   direnv exec . sh scripts/run_matrix.sh
VARIANTS="rr_merge_pipe rr_merge_pipe_stall1 rr_merge_pipe_stall2 rr_merge_pipe_elastic1
          rr_merge_pipe_elastic2 rr_merge_pipe_credit1 rr_merge_pipe_credit2
          rr_merge_pipe_skid rr_merge_pipe_out1"
S20="1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20"
sum=rundir/rtl/matrix.txt
mkdir -p rundir/rtl
: > $sum
fail=0
for v in $VARIANTS; do
    for cfg in "8 4 $S20" "16 4 1 2 3" "32 4 1 2 3" "8 2 1 2 3"; do
        set -- $cfg; w=$1; n=$2; shift 2
        log=rundir/rtl/${v}_w${w}_n${n}.txt
        if sh scripts/run_rtl.sh rtl/gen/$v.sv $v $w $n "$*" "0 1 2" > $log 2>&1; then r=PASS; else r=FAIL; fail=1; fi
        printf '%-24s W=%-2s N=%s runs=%-3s pass=%-3s %s %s\n' $v $w $n \
            "$(grep -c 'seed=' $log)" "$(grep -c ': .*PASS$' $log)" "$r" \
            "$(grep -m1 'sink=0' $log | sed 's/.*sink=0: //; s/ PASS//')" >> $sum
    done
done
cat $sum
exit $fail
