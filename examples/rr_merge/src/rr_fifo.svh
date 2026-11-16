// A DEPTH-entry FIFO with a registered output. out.valid and out.data are
// sync (registers, written in step()); in.ready is comb: room, or the head
// leaving this cycle, so a full FIFO still takes one beat per cycle while
// it drains. That puts out.ready -> in.ready on a comb path through here.
//
// The head is copied to the out.data register, so `mem` may be overwritten
// at the head's slot in the cycle that pops it. As in the RTL, the data
// registers are not reset.
class rr_fifo #(type T = rr_beat_t, int DEPTH = 2) extends fw_component
        implements fw_combinational, fw_steppable;
    typedef rr_fifo #(T, DEPTH) this_t;
    `fw_component_param_utils(this_t)

    (* fw_sp_comb = "ready" *) fw_rv_sp_in  #(T) in;
    fw_rv_sp_out #(T) out;

    // State, at the width it has as registers.
    T                          mem[DEPTH];
    bit [$clog2(DEPTH)-1:0]    wr, rd;
    bit [$clog2(DEPTH+1)-1:0]  count;    // entries held, the head (out.data) included

    function void build();
        in  = new(null, "in", this);
        out = new(null, "out", this);
    endfunction

    virtual function void comb();
        in.set_ready(count < DEPTH || out.get_ready());
    endfunction

    virtual function void step();
        bit push, pop;
        if (in_reset()) begin
            wr    = 0;
            rd    = 0;
            count = 0;
            out.set_valid(0);
            return;
        end
        push = in.get_valid() && in.get_ready();
        pop  = out.get_valid() && out.get_ready();
        // Blocking updates, in order: push lands before the new head is read,
        // so a beat into an empty FIFO is at `out` after the next edge.
        if (push) begin
            mem[wr] = in.get_data();
            wr      = (wr + 1) % DEPTH;
        end
        if (pop) rd = (rd + 1) % DEPTH;
        count = count + push - pop;
        out.set_valid(count != 0);
        if (count != 0) out.set_data(mem[rd]);
    endfunction
endclass
