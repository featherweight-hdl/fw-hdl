#!/bin/sh
# Show that each pipe_bench check fires: run the bench on rr_merge_pipe (v0)
# with each pipe_mutant mode and expect a FAIL with that check's message.
# Run from examples/rr_merge_pipe after scripts/run_rtl.sh has built v0:
#   direnv exec . sh scripts/run_mutants.sh
bin=rundir/rtl/rr_merge_pipe_w8_n4/obj/Vpipe_rtl_tb
out=rundir/rtl/mutants
mkdir -p $out
fail=0
for m in "1:expected" "2:expected" "3:expected" "4:data changed while stalled"; do
    k=${m%%:*}; msg=${m#*:}
    $bin +verilator+seed+1 +sink=1 +mutant=$k > $out/mutant_$k.log 2>&1
    if grep -q '^FAIL' $out/mutant_$k.log && grep -q "$msg" $out/mutant_$k.log; then
        echo "mutant $k: caught ($(grep -m1 ERROR $out/mutant_$k.log | cut -c1-90))"
    else
        echo "mutant $k: NOT caught, see $out/mutant_$k.log"; fail=1
    fi
done
exit $fail
