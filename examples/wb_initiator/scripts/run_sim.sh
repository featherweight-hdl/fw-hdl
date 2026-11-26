#!/bin/sh
# Build tb/wb_init_tb.sv under Verilator and run it: plain, +rand, and the
# +mut_ws mutant (must FAIL). Logs in rundir/sim/ (or $OUT). Run from
# examples/wb_initiator:
#   direnv exec . sh scripts/run_sim.sh
set -e
root=$(cd ../.. && pwd)
out=${OUT:-rundir/sim}
mkdir -p $out
verilator --binary --timing -Wno-fatal -Wno-lint -Wno-style --timescale 1ns/1ps \
    --top-module wb_init_tb -Mdir $out/obj_dir -o sim \
    +incdir+$root/src +incdir+$root/src/std +incdir+src \
    $root/src/fw_clock_xtor_if.sv $root/src/fw_clock_period_xtor_if.sv $root/src/fw_hdl_pkg.sv \
    $root/src/fw_root.sv $root/src/std/fw_put_xtor_if.sv $root/src/std/fw_std_pkg.sv \
    ref/wb_types_pkg.sv src/wb_init_core_pkg.sv src/wb_init_pkg.sv tb/wb_init_tb.sv \
    > $out/build.log 2>&1 || { tail -30 $out/build.log; exit 1; }
$out/obj_dir/sim > $out/sim.log 2>&1
$out/obj_dir/sim +rand > $out/sim_rand.log 2>&1
$out/obj_dir/sim +mut_ws > $out/sim_mut_ws.log 2>&1
grep -h "PASS\|FAIL" $out/sim.log $out/sim_rand.log $out/sim_mut_ws.log
