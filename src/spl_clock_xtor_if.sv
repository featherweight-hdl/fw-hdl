
interface spl_clock_xtor_if(
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

