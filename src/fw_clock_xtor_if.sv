
interface fw_clock_xtor_if(
    input clock,
    input reset
    );

    reg[31:0]           next;
    reg[31:0]           next_reload;

    always @(posedge clock or posedge reset) begin
        if (reset) begin
            next <= {32{1'b0}};
        end else begin
            if (next != 32'd0) begin
                next_reload = next;
                if (next == 32'd1) begin
                    next <= next_reload;
                end else begin
                    next <= next - 1;
                end
            end
        end
    end

    task automatic tick(int count);
        if (count == 0) begin
            #0;
        end else begin
            repeat (count) begin
                @(posedge clock);
            end
        end
    endtask

//    function void 

endinterface


// The root RESET transactor: the pin side of fw_reset_xtor_bridge (the root
// reset domain). `reset` is active high. It lives in this file, next to the
// clock transactor, because fw_hdl_pkg's bridge holds a virtual of it: every
// file list that compiles the package already lists this file.
//
// No parameters, so `virtual fw_reset_xtor_if` stays one type.
interface fw_reset_xtor_if(
    input clock,
    input reset
    );

    function automatic bit in_reset();
        return reset;
    endfunction

    // Returns at once if reset is already asserted.
    task automatic wait_assert();
        if (!reset) @(posedge reset);
    endtask

    // Returns at the first rising clock edge at which reset is low, or at once
    // if it already is.
    task automatic wait_deassert();
        while (reset) @(posedge clock);
    endtask

endinterface
