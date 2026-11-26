#!/bin/sh
# The lowered core (rtl/gen/wb_init_core.sv, scripts/gen_rtl.py) against
# fw-proto-wb's wb_initiator_xtor_core (ref/), unbounded (yosys/equiv.ys).
# The cores' struct ports become flat vectors in a wrapper; yosys reads both
# through sv2v. Logs in rundir/equiv/ (or $OUT). Run from examples/wb_initiator:
#   direnv exec . sh scripts/equiv.sh [rtl/gen/wb_init_core.sv]
gen=${1:-rtl/gen/wb_init_core.sv}
out=${OUT:-rundir/equiv}
mkdir -p $out
wrap() {    # <name> <module> <bus prefix> <out suffix> <dat_w suffix> <dat_r suffix> <in suffix>
    cat > $out/$1.top.sv <<EOT
module meas_top (
    input  logic clock, reset,
    input  logic req_valid, output logic req_ready, input logic [69:0] req_data,
    output logic rsp_valid, input logic rsp_ready, output logic [33:0] rsp_data,
    output logic [31:0] adr, dat_w, output logic [3:0] sel,
    output logic we, cyc, stb,
    input  logic [31:0] dat_r, input logic ack, err, rty);
    $2 dut (.clock, .reset, .req_valid, .req_ready, .req_data, .rsp_valid, .rsp_ready, .rsp_data,
        .${3}adr$4(adr), .${3}dat$5(dat_w), .${3}sel$4(sel), .${3}we$4(we), .${3}cyc$4(cyc),
        .${3}stb$4(stb), .${3}dat$6(dat_r), .${3}ack$7(ack), .${3}err$7(err), .${3}rty$7(rty));
endmodule
EOT
}
wrap ref wb_initiator_xtor_core "" _o _o _i _i
wrap gen wb_init_core wb_ "" _w _r ""
sv2v ref/wb_types_pkg.sv ref/wb_initiator_xtor_core.sv $out/ref.top.sv > $out/ref.v || exit 1
sv2v $gen $out/gen.top.sv > $out/gen.v || exit 1
sed "s|@OUT@|$out|" yosys/equiv.ys > $out/equiv.ys
if yosys -q -l $out/equiv.log $out/equiv.ys > /dev/null 2>&1; then
    echo "equiv wb_init_core = wb_initiator_xtor_core: proven (unbounded)"
else
    echo "equiv wb_init_core = wb_initiator_xtor_core: NOT proven, see $out/equiv.log"; exit 1
fi
