
// fw_arbiter -- an N-input arbiter (accept then arbitrate).
//
//   in[N]  the inputs (streams, polled: fw_get_nb_if);
//   out    {index, value}: which input won, and its value (a stream: out may
//          back-pressure, fw_put_step_if).
//
// Each input has a one-value hold, and an input is ready while its hold is
// empty. Among the held values, POLICY picks one:
//   FW_ARB_RR    round robin: the first held input after the last winner;
//                input 0 goes first;
//   FW_ARB_PRIO  fixed priority: the lowest held index.
//
// Per cycle:
//   observes  the holds at the start of the cycle (never a value arriving in
//             it: the grant does not depend on same-cycle valid);
//   consumes  one held value when out accepts it; every empty hold, and the
//             hold granted this cycle, takes its input. So an input is ready
//             while its hold is empty or granted, every ready comes from
//             registered state, and one input alone streams at full rate. A
//             value is offered from the cycle after it arrives;
//   ties      by POLICY, as above;
//   back-pressure  stalls the whole arbiter: out keeps offering the same
//             value, no hold fills, and the round-robin pointer moves only
//             when out accepts. So round robin here is already "fair" (it
//             advances on accept only).
//
// The class is an all-or-nothing step (fw_atomic_step): one grant per cycle,
// and a cycle whose grant finds out not ready has no effect at all. So the
// model is cycle-exact, and step() is what fw-hdl lowers. Its state is one
// packed struct, zero at reset; `nxt` is the input after the last winner.
typedef enum int {FW_ARB_RR, FW_ARB_PRIO} fw_arb_policy_e;

// fw_arbiter's state (a class only to carry the parameters).
class fw_arbiter_state #(type T = bit [7:0], int N = 2);
    localparam int IB = (N > 1) ? $clog2(N) : 1;
    typedef struct packed {
        bit [N-1:0]  hv;        // hold k is full
        T [N-1:0]    hold;
        bit [IB-1:0] nxt;       // round robin: the first input to look at
    } t;
endclass

class fw_arbiter #(type T = bit [7:0], int N = 2, fw_arb_policy_e POLICY = FW_ARB_RR)
        extends fw_atomic_step #(fw_arbiter_state #(T, N)::t);
    localparam int IB = (N > 1) ? $clog2(N) : 1;
    fw_port #(fw_get_nb_if #(T))                      in[N];
    fw_port #(fw_put_step_if #(bit [IB+$bits(T)-1:0])) out;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        foreach (in[i]) in[i] = new($sformatf("in[%0d]", i), this);
        out = new("out", this);
    endfunction

    // Grant over the holds full at the start of the cycle, then refill every
    // hold that was empty or is granted.
    virtual function void step();
        T            x;
        bit          found;
        bit [IB-1:0] g, k;
        for (int j = 0; j < N; j++) begin
            if (POLICY == FW_ARB_RR)
                k = (int'(s.nxt) + j >= N) ? IB'(int'(s.nxt) + j - N) : IB'(int'(s.nxt) + j);
            else
                k = IB'(j);
            if (!found && s.hv[k]) begin
                found = 1'b1;
                g = k;
            end
        end
        if (found) begin
            out.t.put_or_stall({g, s.hold[g]});
            s.hv[g] = 1'b0;
            s.nxt = (int'(g) + 1 >= N) ? '0 : g + IB'(1);
        end
        for (int i = 0; i < N; i++) begin
            if (!s.hv[i] && in[i].t.try_get(x)) begin
                s.hold[i] = x;
                s.hv[i] = 1'b1;
            end
        end
    endfunction
endclass
