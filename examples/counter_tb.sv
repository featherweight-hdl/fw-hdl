
module counter_tb;
    reg clock = 0;
    reg reset = 1;
    reg[31:0] count;

    counter u_counter(
        .clock(clock),
        .reset(reset),
        .count(count)
    );

    initial begin
        #100ns;
        reset = 0;
        #100ns;
        reset = 1;
        #100ns;
        reset = 0;
    end

    initial begin
        forever begin
            #5ns;
            clock <= ~clock;
        end
    end

    initial begin
        #1ms;
        $finish;
    end

endmodule

