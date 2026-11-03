
// fw_arbiter -- an N-input arbiter (accept then arbitrate).
//
//   in[N]  the inputs (streams);
//   out    {index, value}: which input won, and its value.
//
// Each input has a one-entry hold: an input is ready while its hold is empty.
// Among the held values, POLICY picks one:
//   FW_ARB_RR    round robin: the first held input after the last winner;
//                input 0 goes first;
//   FW_ARB_PRIO  fixed priority: the lowest held index.
// A grant is not taken back: the winner's hold empties only when out accepts.
//
// Values from one input leave in their order; the interleaving across inputs
// depends on timing. Compare views per input (fw.hdl.verif.canon
// Rule(per_key=True), the index as the key). Recognized by the registry (xls:
// FW_ARB_RR only): the body below is the model and is not mapped.
typedef enum int {FW_ARB_RR, FW_ARB_PRIO} fw_arb_policy_e;

class fw_arbiter #(type T = bit [7:0], int N = 2, fw_arb_policy_e POLICY = FW_ARB_RR)
        extends fw_component implements fw_runnable;
    localparam int IB = (N > 1) ? $clog2(N) : 1;
    fw_port #(fw_get_if #(T))                   in[N];
    fw_port #(fw_put_if #(bit [IB+$bits(T)-1:0])) out;
    protected T          m_hold[N];
    protected bit [N-1:0] m_hv;
    protected int        m_last = N - 1;
    protected event      m_filled, m_freed;

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
            ->m_filled;
        end
    endtask

    virtual task run();
        for (int i = 0; i < N; i++) begin
            fork
                automatic int k = i;
                fill(k);
            join_none
        end
        forever begin
            int g;
            while (m_hv == '0) @(m_filled);
            g = pick();
            out.t.put({IB'(g), m_hold[g]});
            m_hv[g] = 1'b0;
            m_last = g;
            ->m_freed;
        end
    endtask
endclass
