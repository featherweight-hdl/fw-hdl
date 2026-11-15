#!/bin/bash
# Usage: run_sim.sh <name> <tb> [STEP]  -- simulates out/<name>.funcsim.v (post-synthesis netlist) in xsim
set -e
n=$1; tb=$2; step=${3:-1}
w=sim/work_$n; rm -rf $w; mkdir -p $w; cd $w
xvlog -sv ../../out/$n.funcsim.v ../$tb > xvlog.log 2>&1
xvlog $XILINX_VIVADO/data/verilog/src/glbl.v >> xvlog.log 2>&1
xelab -L unisims_ver tb glbl -generic_top STEP=$step -s snap > xelab.log 2>&1
xsim snap -R > xsim.log 2>&1
grep -h -E 'SIMRESULT|MISMATCH' xsim.log | head -3
