// T5 hand-written reference (docs/design/xtor-shell-plan.md): the target's
// shell. Its ports are the bus pins and the clock only; it holds the
// lowered core (wb_target_xtor_core, emitted by emit_core.py) and the
// interface u_if, joined on the core's crossing ports. Same form as
// wb_initiator_xtor; the core here has state (busy), so it takes the clock.
module wb_target_xtor(
    input  logic        clock,
    input  logic [31:0] adr,
    input  logic [31:0] dat_w,
    input  logic [3:0]  sel,
    input  logic        we,
    input  logic        cyc,
    input  logic        stb,
    output logic [31:0] dat_r,
    output logic        ack,
    output logic        err
);
    wb_target_xtor_if u_if(.clock(clock));

    wb_target_xtor_core u_core(
        .clk(clock),
        .pins_adr(adr), .pins_dat_w(dat_w), .pins_sel(sel), .pins_we(we),
        .pins_cyc(cyc), .pins_stb(stb), .pins_dat_r(dat_r), .pins_ack(ack),
        .pins_err(err),
        .reqs_valid(u_if.reqs_valid), .reqs_ready(u_if.reqs_ready),
        .reqs_data(u_if.reqs_data),
        .rsps_valid(u_if.rsps_valid), .rsps_ready(u_if.rsps_ready),
        .rsps_data(u_if.rsps_data));
endmodule
