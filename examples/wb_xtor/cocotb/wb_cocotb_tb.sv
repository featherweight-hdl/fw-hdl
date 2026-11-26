// T7 bench (docs/design/xtor-shell-plan.md, D9): the generated initiator
// and target cores back to back on the bus, with no SV interface or shell.
// Their crossing ports are left open: the cocotb bridges drive and sample
// them through the cores' handles (dut.xi, dut.xt). cocotb drives clk.
module wb_cocotb_tb(input logic clk);
    logic [31:0] adr, dat_w, dat_r;
    logic [3:0]  sel;
    logic        we, cyc, stb, ack, err;

    wb_initiator_xtor_core xi(.pins_adr(adr), .pins_dat_w(dat_w), .pins_sel(sel),
                              .pins_we(we), .pins_cyc(cyc), .pins_stb(stb),
                              .pins_dat_r(dat_r), .pins_ack(ack), .pins_err(err),
                              .reqs_valid(), .reqs_ready(), .reqs_data(),
                              .rsps_valid(), .rsps_ready(), .rsps_data());
    wb_target_xtor_core    xt(.clk(clk), .pins_adr(adr), .pins_dat_w(dat_w), .pins_sel(sel),
                              .pins_we(we), .pins_cyc(cyc), .pins_stb(stb),
                              .pins_dat_r(dat_r), .pins_ack(ack), .pins_err(err),
                              .reqs_valid(), .reqs_ready(), .reqs_data(),
                              .rsps_valid(), .rsps_ready(), .rsps_data());
endmodule
