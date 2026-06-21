
interface fw_put_xtor_if #(
    parameter type T = int
) (
    output T        out
);

    task automatic put(input T t);
        out <= t;
    endtask

endinterface

