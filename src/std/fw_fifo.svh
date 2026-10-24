// A FIFO that a lowered design can count, peek and flush: packed storage and
// two pointers, one bit wider than the index. Unlike fw_channel it has no
// queue, so its simulation state is the state the lowering builds (flops and
// a read mux).
//
// Each side writes only its own pointer, so a writer process and a reader
// process can push and pop in the same clock without losing either:
//   writer side  push(), full(), wr_ptr (and the entry it writes)
//   reader side  head(), pop(), empty(), rd_ptr
//   either       count(), a relation over the two pointers
//
// flush() sets rd_ptr = wr_ptr. Called from the reader side it is a
// single-writer write. Called from the writer side it is a second writer of
// rd_ptr: the caller must win over the reader by the lowering's priority (a
// bridge context over a model process), and a pop in the same clock is
// overridden.
//
// push() when full is a caller error: it is reported in simulation and the
// value is dropped (never overwrites). pop() when empty does nothing.
// DEPTH must be a power of two.
class fw_fifo #(type T = bit [7:0], int DEPTH = 16);
    localparam int AW = (DEPTH > 1) ? $clog2(DEPTH) : 1;

    bit [DEPTH-1:0][$bits(T)-1:0] mem;
    bit [AW:0]                    wr_ptr;
    bit [AW:0]                    rd_ptr;

    function new();
        if ((DEPTH & (DEPTH - 1)) != 0 || DEPTH < 2)
            $fatal(1, "fw_fifo: DEPTH (%0d) must be a power of two, >= 2", DEPTH);
    endfunction

    // ---- either side ----
    // empty() and full() compare the pointers: through count() they would
    // be a subtractor and a compare, a carry chain deeper than the XORs.
    // empty() is an XOR reduction, not `wr_ptr == rd_ptr`: Yosys (alumacc)
    // merges an equality with a subtraction of the same operands, so where
    // count() is used too the compare would become the subtractor's zero
    // test.
    function bit [AW:0] count(); return wr_ptr - rd_ptr; endfunction
    function bit empty();        return ~|(wr_ptr ^ rd_ptr); endfunction
    function bit full();         return wr_ptr == {~rd_ptr[AW], rd_ptr[AW-1:0]}; endfunction

    // ---- writer side ----
    function void push(T v);
        if (full()) begin
            $error("fw_fifo: push when full; the value is dropped");
            return;
        end
        for (int i = 0; i < DEPTH; i++)
            if (wr_ptr[AW-1:0] == AW'(i)) mem[i] = $bits(T)'(v);
        wr_ptr = wr_ptr + 1'b1;
    endfunction

    // ---- reader side ----
    function T head(); return T'(at(rd_ptr[AW-1:0])); endfunction

    function void pop();
        if (!empty()) rd_ptr = rd_ptr + 1'b1;
    endfunction

    // The entry `i` places behind the head (0 is the head).
    function T peek(bit [AW-1:0] i); return T'(at(rd_ptr[AW-1:0] + i)); endfunction

    function void flush(); rd_ptr = wr_ptr; endfunction

    // Entry `idx`. Indexing the packed storage with a run-time index lowers
    // to a shifter over all of it; an AND-OR over constant indices is a
    // decoder and a read mux, as a memory's read port maps. push() writes
    // with constant indices for the same reason.
    protected function bit [$bits(T)-1:0] at(bit [AW-1:0] idx);
        bit [$bits(T)-1:0] r = '0;
        for (int i = 0; i < DEPTH; i++)
            r = r | (mem[i] & ((idx == AW'(i)) ? '1 : '0));
        return r;
    endfunction
endclass
