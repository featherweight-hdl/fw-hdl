// pipe_bench on the rr_merge_pipe classes (variant v0, W = 8, N = 4) under a
// clocked fw_root: the bench's pins -> fw_rv_pin_in -> rr_merge_pipe ->
// fw_rv_pin_out -> the bench. The same bench runs the generated RTL
// (pipe_rtl_tb.sv).
import fw_hdl_pkg::*;
import pipe_types_pkg::*;
import rr_merge_pipe_pkg::*;

class pipe_root extends fw_component_root #(fw_component);
    rr_merge_pipe4_t dut;

    function new(string name);
        super.new(name);
    endfunction

    virtual function void build();
        dut = rr_merge_pipe4_t::type_id::create("dut", this);
    endfunction

    virtual function void connect();
        foreach (dut.in[i])
            fw_rv_pin #(pipe_in8_t)::find($sformatf("in%0d", i)).connect_in(dut.in[i]);
        fw_rv_pin #(pipe_mid8_t)::find("out").connect_out(dut.out);
    endfunction
endclass

module pipe_cls_tb;
    localparam int N = 4;

    logic           clk = 0, rst;
    always #5 clk = ~clk;
    logic [N-1:0]     in_valid, in_ready;
    pipe_in8_t [N-1:0] in_data;
    logic             out_valid, out_ready;
    pipe_mid8_t       out_data;

    pipe_bench #(.N(N), .TI(pipe_in8_t), .TM(pipe_mid8_t), .NAME("rr_merge_pipe (classes)"))
        bench (.*);

    sv_weave_init_m u_init();
    fw_root #(.Tbind(pipe_root)) u_root (.clock(clk), .reset(rst));

    // A pin value lands in the tree at once (fw_rv_pin).
    fw_rv_pin_in  #(.T(pipe_in8_t), .NAME("in0")) u_in0 (
        .valid(in_valid[0]), .data(in_data[0]), .ready(in_ready[0]));
    fw_rv_pin_in  #(.T(pipe_in8_t), .NAME("in1")) u_in1 (
        .valid(in_valid[1]), .data(in_data[1]), .ready(in_ready[1]));
    fw_rv_pin_in  #(.T(pipe_in8_t), .NAME("in2")) u_in2 (
        .valid(in_valid[2]), .data(in_data[2]), .ready(in_ready[2]));
    fw_rv_pin_in  #(.T(pipe_in8_t), .NAME("in3")) u_in3 (
        .valid(in_valid[3]), .data(in_data[3]), .ready(in_ready[3]));
    fw_rv_pin_out #(.T(pipe_mid8_t), .NAME("out")) u_out (
        .valid(out_valid), .data(out_data), .ready(out_ready));

    initial begin
        wait (bench.done);
        if (bench.errors != 0) $fatal(1, "FAIL");
        $finish;
    end
endmodule
