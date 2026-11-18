#!/bin/sh
# Build and run both probes; compare traces to expected_*.txt.
# Usage: direnv exec /packets/featherweight-hdl/fw-hdl-sync sh run.sh
set -e
cd "$(dirname "$0")"
mkdir -p obj_dir
verilator --binary --timing --sched-zero-delay -j 0 top.sv > obj_dir/build.log 2>&1
verilator --binary --timing --sched-zero-delay -j 0 --top-module top2 --Mdir obj_dir/top2 top2.sv > obj_dir/build2.log 2>&1
./obj_dir/Vtop | grep -v '^- ' | diff expected_top.txt -
./obj_dir/top2/Vtop2 | grep -v '^- ' | diff expected_top2.txt -
echo "l2-timing: PASS"
