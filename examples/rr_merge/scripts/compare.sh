#!/bin/sh
# Synthesize the generated and the reference rr_merge with yosys (generic
# gates) and check that they are equivalent:
#   - unbounded: yosys/equiv.ys (equiv_make pairs the same-named state of the
#     two, equiv_induct proves it by induction) over a grid of N x DEPTH;
#   - bounded from reset: yosys/bmc.ys on yosys/rr_merge_miter.sv, 40 cycles,
#     at a few points.
# Both designs are parameterized with `parameter type T`, which yosys's reader
# lacks, so both are read through sv2v. Logs go to rundir/compare/. Run from
# examples/rr_merge:
#   direnv exec . sh scripts/compare.sh
set -e
out=rundir/compare
mkdir -p $out
sv2v rtl/gen/rr_merge.sv > $out/rr_merge_gen.v
sv2v rtl/rr_merge_ref.sv > $out/rr_merge_ref.v
synth() {   # <name> <top>
    yosys -q -l $out/synth_$1.log \
        -p "read_verilog $out/rr_merge_$1.v; hierarchy -top $2; synth -top $2; \
            tee -q -o $out/stat_$1.txt stat; flatten; synth -top $2; \
            tee -q -o $out/stat_$1_flat.txt stat" > /dev/null
    printf '%-4s %s cells (by module), %s flattened, flops: %s\n' $1 \
        "$(grep -E '^ +[0-9]+ cells$' $out/stat_$1.txt | tail -1 | awk '{print $1}')" \
        "$(grep -E '^ +[0-9]+ cells$' $out/stat_$1_flat.txt | awk '{print $1}')" \
        "$(grep -E 'DFF' $out/stat_$1_flat.txt | awk '{s+=$1} END {print s}')"
}
synth gen rr_merge
synth ref rr_merge_ref
fail=0
for n in 2 3 4 5 8; do
    for d in 1 2 3 4 8; do
        sed "s/@N@/$n/; s/@DEPTH@/$d/" yosys/equiv.ys > $out/equiv_${n}_$d.ys
        if yosys -q -l $out/equiv_${n}_$d.log $out/equiv_${n}_$d.ys > /dev/null 2>&1; then
            echo "equiv N=$n DEPTH=$d: proven (unbounded)"
        else
            echo "equiv N=$n DEPTH=$d: NOT proven, see $out/equiv_${n}_$d.log"; fail=1
        fi
    done
done
for nd in 4:2 4:3 3:2; do
    n=${nd%:*}; d=${nd#*:}
    sed "s/@N@/$n/; s/@DEPTH@/$d/" yosys/bmc.ys > $out/bmc_${n}_$d.ys
    if yosys -q -l $out/bmc_${n}_$d.log $out/bmc_${n}_$d.ys > /dev/null 2>&1; then
        echo "bmc N=$n DEPTH=$d: equivalent for 40 cycles from reset"
    else
        echo "bmc N=$n DEPTH=$d: FAIL, see $out/bmc_${n}_$d.log"; fail=1
    fi
done
exit $fail
