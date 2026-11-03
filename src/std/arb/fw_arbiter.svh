
// fw_arbiter -- an N-input arbiter (accept then arbitrate).
//
//   in[N]  the inputs (streams);
//   out    {index, value}: which input won, and its value (a stream: out may
//          back-pressure).
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
// The body below is the class model, a process: one grant per clock over
// the holds full at that edge, blocking while out back-pressures. Its holds
// fill as values arrive, and may fill while out stalls, so it is not
// cycle-exact. Values from one input leave in their order; the interleaving
// across inputs depends on timing. Compare views per input
// (fw.hdl.verif.canon Rule(per_key=True), the index as the key; contract in
// fw_arbiter.yaml). The RTL's per-cycle rules are checked on the RTL
// (tests/xls/lib/test_arbiter.py). Recognized by the registry: the body is
// not mapped.
typedef enum int {FW_ARB_RR, FW_ARB_PRIO} fw_arb_policy_e;

class fw_arbiter #(type T = bit [7:0], int N = 2, fw_arb_policy_e POLICY = FW_ARB_RR)
        extends fw_component implements fw_runnable;
    localparam int IB = (N > 1) ? $clog2(N) : 1;
    fw_port #(fw_get_if #(T))                   in[N];
    fw_port #(fw_put_if #(bit [IB+$bits(T)-1:0])) out;
    protected T          m_hold[N];
    protected bit [N-1:0] m_hv;
    protected int        m_last = N - 1;
    protected event      m_freed;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);
    endfunction

    function void build();
        foreach (in[i]) in[i] = new($sformatf("in[%0d]", i), this);
        out = new("out", this);
    endfunction

    protected function int pick();
        for (int j = 1; j <= N; j++) begin
            int k = (POLICY == FW_ARB_RR) ? (m_last + j) % N : j - 1;
            if (m_hv[k]) return k;
        end
        return -1;
    endfunction

    protected task fill(int k);
        forever begin
            T x;
            while (m_hv[k]) @(m_freed);
            in[k].t.get(x);
            m_hold[k] = x;
            m_hv[k] = 1'b1;
        end
    endtask

    virtual task run();
        for (int i = 0; i < N; i++) begin
            fork
                automatic int k = i;
                fill(k);
            join_none
        end
        // One grant per clock, over the holds full at that edge. A value
        // held during a cycle can win from the next edge, as in the RTL.
        forever begin
            int g;
            tick();
            if (m_hv == '0)
                continue;
            g = pick();
            out.t.put({IB'(g), m_hold[g]});
            m_hv[g] = 1'b0;
            m_last = g;
            ->m_freed;
        end
    endtask
endclass
