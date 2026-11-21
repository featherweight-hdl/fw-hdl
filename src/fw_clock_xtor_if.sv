
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

    // The root's edges, counted from time 0 (fw-hdl-spec processes.md,
    // "Edges"): a rise to 1 from any other value, so 0 -> X -> 1 is one
    // edge. Read by the root's edge driver (fw_edge_driver_net).
    longint unsigned n_edges;

    always @(posedge clock) if (clock === 1'b1) n_edges++;

    // Returns once edge k has come.
    task automatic wait_edges(longint unsigned k);
        while (n_edges < k) @(n_edges);
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
