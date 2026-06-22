
interface fw_put_xtor_if #(
    parameter type T = int
) (
    input clock,
    input reset,
    output T        out
);

    task automatic put(input T t);
        @(posedge clock);
        out <= t;
    endtask

endinterface

