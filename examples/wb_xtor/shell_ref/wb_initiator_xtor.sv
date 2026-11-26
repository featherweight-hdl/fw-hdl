// T0 hand-written reference (docs/design/xtor-shell-plan.md): the shell.
// Its ports are the bus pins and the clock only; it holds the lowered core
// (wb_initiator_xtor_core, emitted by emit_core.py) and the interface
// u_if, joined on the core's crossing ports. Synthesizable apart from the
// interface's tasks; nothing registers itself (the HVL side is given u_if).
module wb_initiator_xtor(
    input  logic        clock,
    output logic [31:0] adr,
    output logic [31:0] dat_w,
    output logic [3:0]  sel,
    output logic        we,
    output logic        cyc,
    output logic        stb,
    input  logic [31:0] dat_r,
    input  logic        ack,
    input  logic        err
);
    wb_initiator_xtor_if u_if(.clock(clock));

    wb_initiator_xtor_core u_core(
        .pins_adr(adr), .pins_dat_w(dat_w), .pins_sel(sel), .pins_we(we),
        .pins_cyc(cyc), .pins_stb(stb), .pins_dat_r(dat_r), .pins_ack(ack),
        .pins_err(err),
        .reqs_valid(u_if.reqs_valid), .reqs_ready(u_if.reqs_ready),
        .reqs_data(u_if.reqs_data),
        .rsps_valid(u_if.rsps_valid), .rsps_ready(u_if.rsps_ready),
        .rsps_data(u_if.rsps_data));
endmodule
