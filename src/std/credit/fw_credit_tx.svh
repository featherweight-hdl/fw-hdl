// fw_credit_tx -- a credit-gated sender over NVC virtual channels, with a
// shared pool and a per-VC reserve.
//
//   in[NVC]  the values to send, one stream per VC;
//   cr       credit returns: each value is the VC one credit comes back to;
//   out      {vc, value}, valid-only: a value is offered only when its credits
//            are held, so the receiver never has to stall it.
//
// Credits. The receiver's buffer is CREDITS credits. At reset they fill each
// VC's reserve (RESERVE credits) in VC order and the rest go to the pool.
// A value on VC v may be sent when pool + reserve[v] >= CHECK, and spends
// CHECK credits: POLICY FW_CREDIT_POOL_FIRST takes them from the pool first,
// FW_CREDIT_VC_FIRST from the VC's reserve first. A returned credit refills
// its VC's reserve up to RESERVE, then the pool. With RESERVE = 0 every
// credit is in the pool.
//
// Per cycle (step):
//   observes  the credits and holds at the start of the cycle, and one
//             credit return;
//   consumes  at most one value (one send) and one credit return;
//   ties      NVC > 1: round robin over the VCs whose hold is full and whose
//             credits cover CHECK, from the VC after the last one sent;
//   same-cycle valid  never decides a send. Every ready is a function of
//             registered state: in[v] is ready while v can take a value (see
//             below), cr is always ready, so a credit return never waits
//             behind data.
// A credit returned in a cycle can be spent from the next cycle.
//
// NVC = 1 has no hold: in[0] is ready while the credits cover CHECK, and a
// value taken is sent in the same cycle (the credit_tx shape). NVC > 1 has a
// one-value hold per VC: in[v] is ready while hold v is empty, or is sent this
// cycle; a value is sent from the cycle after it arrives.
typedef enum int {FW_CREDIT_POOL_FIRST, FW_CREDIT_VC_FIRST} fw_credit_policy_e;

class fw_credit_tx #(type T = bit [7:0], int CREDITS = 2, int NVC = 1, int RESERVE = 0,
        fw_credit_policy_e POLICY = FW_CREDIT_POOL_FIRST, int CHECK = 1)
        extends fw_component implements fw_steppable;
    localparam int VB = (NVC > 1) ? $clog2(NVC) : 1;
    localparam int CB = $clog2(CREDITS + 1);
    typedef bit [CB-1:0] cnt_t;
    typedef cnt_t        res_t[NVC];

    fw_port #(fw_get_nb_if #(T))                    in[NVC];
    fw_port #(fw_get_nb_if #(bit [VB-1:0]))         cr;
    fw_port #(fw_valid_put_if #(bit [VB+$bits(T)-1:0])) out;

    // The reset split: reserves in VC order, then the pool.
    static function res_t init_res();
        int left = CREDITS;
        for (int v = 0; v < NVC; v++) begin
            init_res[v] = cnt_t'((left < RESERVE) ? left : RESERVE);
            left -= int'(init_res[v]);
        end
    endfunction
    localparam res_t INIT_RES = init_res();
    localparam int   INIT_POOL = (CREDITS > NVC * RESERVE) ? CREDITS - NVC * RESERVE : 0;

    protected cnt_t      m_pool = cnt_t'(INIT_POOL);
    protected res_t      m_res = INIT_RES;
    protected T          m_hold[NVC];
    protected bit [NVC-1:0] m_hv;
    protected bit [VB-1:0]  m_last = VB'(NVC - 1);

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_steppable(this);
    endfunction

    function void build();
        foreach (in[i]) in[i] = new($sformatf("in[%0d]", i), this);
        cr = new("cr", this);
        out = new("out", this);
    endfunction

    // The smaller of a and b.
    static function cnt_t min_c(cnt_t a, cnt_t b);
        return (a < b) ? a : b;
    endfunction

    // Each cycle: send at most one value and spend its credits, refill the
    // holds (NVC > 1), then take one credit return.
    virtual function void step();
        T            x;
        bit [VB-1:0] r;
        bit          found;
        bit [VB-1:0] g, v;
        cnt_t        a;
        if (NVC == 1) begin
            if (int'(m_pool) + int'(m_res[0]) >= CHECK && in[0].t.try_get(x)) begin
                out.t.put({VB'(0), x});
                found = 1'b1;
                g = '0;
            end
        end else begin
            for (int k = 1; k <= NVC; k++) begin
                v = (int'(m_last) + k >= NVC) ? VB'(int'(m_last) + k - NVC)
                                               : VB'(int'(m_last) + k);
                if (!found && m_hv[v] && int'(m_pool) + int'(m_res[v]) >= CHECK) begin
                    found = 1'b1;
                    g = v;
                end
            end
            if (found) begin
                out.t.put({g, m_hold[g]});
                m_hv[g] = 1'b0;
                m_last = g;
            end
        end
        if (found) begin
            if (POLICY == FW_CREDIT_POOL_FIRST) begin
                a = min_c(m_pool, cnt_t'(CHECK));
                m_pool = m_pool - a;
                m_res[g] = m_res[g] - (cnt_t'(CHECK) - a);
            end else begin
                a = min_c(m_res[g], cnt_t'(CHECK));
                m_res[g] = m_res[g] - a;
                m_pool = m_pool - (cnt_t'(CHECK) - a);
            end
        end
        if (NVC > 1) begin
            for (int k = 0; k < NVC; k++) begin
                if (!m_hv[k] && in[k].t.try_get(x)) begin
                    m_hold[k] = x;
                    m_hv[k] = 1'b1;
                end
            end
        end
        // A returned credit refills its VC's reserve, then the pool.
        if (cr.t.try_get(r)) begin
            if (int'(r) >= NVC)
                ;
            else if (int'(m_res[r]) < RESERVE)
                m_res[r] = m_res[r] + cnt_t'(1);
            else
                m_pool = m_pool + cnt_t'(1);
        end
    endfunction
endclass
