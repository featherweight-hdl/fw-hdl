// Do the two Verilator 5.049 bugs noted in
// rv_proto_tb.sv still occur on the packet's Verilator?
//   A. a `type`-parameterized interface as a MODULE PORT (5.049: V3Param crash)
//   B. a `type`-parameterized interface INSTANCE whose input ports are driven
//      from outside (5.049: the interface saw 0)
// Also covers C: a virtual handle of the parameterized type, written from a
// class, as the rv bridges do.
// Variants (defines): NO_PORT drops A; BARE_PORT declares the module port
// without parameters (inferred from the connection).
typedef struct packed { logic [3:0] tag; logic [11:0] val; } beat_t;

interface k1_rv_if #(type T = logic [31:0]) (input logic clock, input logic valid,
                                           input T data, output logic ready);
    T     last;
    int   n;
    initial n = 0;
    assign ready = 1'b1;
    always @(posedge clock) if (valid) begin last <= data; n <= n + 1; end
endinterface

// A: the interface as a module port; the module samples through it.
`ifdef BARE_PORT
module k1_consumer #(type T = logic [31:0]) (k1_rv_if port, output T seen);
`else
module k1_consumer #(type T = logic [31:0]) (k1_rv_if #(T) port, output T seen);
`endif
    always @(posedge port.clock) if (port.valid) seen <= port.data;
endmodule

class k1_driver #(type T = logic [31:0]);
    virtual k1_rv_if #(T) vif;
    function new(virtual k1_rv_if #(T) vif); this.vif = vif; endfunction
    function T peek(); return vif.last; endfunction
endclass

module k1_typeparam;
    logic clock = 0;
    always #5 clock = ~clock;
    logic  valid = 0, ready8, readys;
    logic [7:0] d8 = 0;
    beat_t ds = '0;
    logic [7:0] seen8;
    beat_t seens;

    // B: instances driven from outside, at two types.
    k1_rv_if #(logic [7:0]) i8 (.clock(clock), .valid(valid), .data(d8), .ready(ready8));
    k1_rv_if #(beat_t)      is (.clock(clock), .valid(valid), .data(ds), .ready(readys));
    // A: each passed to a module port.
`ifndef NO_PORT
    k1_consumer #(logic [7:0]) c8 (.port(i8), .seen(seen8));
    k1_consumer #(beat_t)      cs (.port(is), .seen(seens));
`else
    always @(posedge clock) if (valid) begin seen8 <= d8; seens <= ds; end
`endif

    initial begin
        k1_driver #(beat_t) drv = new(is);
        int errs = 0;
        @(negedge clock);
        valid = 1; d8 = 8'hA5; ds = '{tag: 4'h3, val: 12'hBEE};
        @(negedge clock);
        valid = 0;
        @(negedge clock);
        if (i8.n != 1 || i8.last != 8'hA5)  begin errs++; $display("B8 FAIL n=%0d last=%h", i8.n, i8.last); end
        if (is.n != 1 || is.last != ds)     begin errs++; $display("Bs FAIL n=%0d last=%h", is.n, is.last); end
        if (seen8 != 8'hA5)                 begin errs++; $display("A8 FAIL seen=%h", seen8); end
        if (seens != ds)                    begin errs++; $display("As FAIL seen=%h", seens); end
        if (drv.peek() != ds)               begin errs++; $display("C FAIL peek=%h", drv.peek()); end
        if (!ready8 || !readys)             begin errs++; $display("ready FAIL"); end
        if (errs == 0) $display("K1 PASS"); else $display("K1 FAIL (%0d)", errs);
        $finish;
    end
endmodule
