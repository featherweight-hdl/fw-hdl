// fw_dep_tracker -- dependents that wait for the youngest older producer.
//
//   ent  {kind, id}, one a cycle in the source's order (fw_get_nb_if):
//        kind 0, a producer with tag id (0 .. N-1) enters;
//        kind 1, a dependent with tag id (0 .. M-1) enters;
//   ret  a producer's tag: it retires (fw_get_nb_if, always taken);
//   ok   bit d is set while dependent d is not waiting (fw_level_set_if).
//
// A dependent waits on the youngest producer that is live when it enters,
// and only on that one: it is released when that producer retires, even if
// an older one is still live (sticky). Producers retire in any order. The
// user's tags name both, so a retire names its producer with the tag its
// completion carries; a dependent's next entry overwrites its slot.
//
// Per cycle (step):
//   observes  the live producers, their order and the waiting dependents at
//             the start of the cycle;
//   consumes  at most one entry and one retire;
//   dependent waits on the youngest live producer, or on none (then ok[d]
//             is set from the next cycle);
//   retire    releases every dependent waiting on that producer, including
//             one that entered in the same cycle and recorded it;
//   ok        is the state at the start of the next cycle, so a dependent
//             is released the cycle after its producer's retire is taken;
//   misuse    retiring a producer that is not live, or entering one that
//             is, does nothing;
//   same-cycle valid  never decides anything: ent and ret are always
//             ready, and ok is a level, so the tracker never stalls.
//
// The live producers are a list in entry order: each has a link to the one
// that entered before it, and `top` is the youngest. A retire unlinks its
// producer; a later producer's link is moved past it by a compare per slot,
// so the order is exact however long a producer stays live. Every update is
// a mask over the slots. At reset nothing is live and no dependent waits.
class fw_dep_tracker #(int N = 32, int M = 32) extends fw_component implements fw_steppable;
    localparam int PB = (N > 1) ? $clog2(N) : 1;
    localparam int DB = (M > 1) ? $clog2(M) : 1;
    localparam int IB = (PB > DB) ? PB : DB;

    fw_port #(fw_get_nb_if #(bit [IB:0]))    ent;
    fw_port #(fw_get_nb_if #(bit [PB-1:0]))  ret;
    fw_port #(fw_level_set_if #(bit [M-1:0])) ok;

    protected bit [N-1:0]          m_live;
    protected bit [N-1:0][PB-1:0]  m_prev;     // the producer that entered before
    protected bit [N-1:0]          m_pv;       // ... and is still live
    protected bit [PB-1:0]         m_top;      // the youngest live producer
    protected bit                  m_tv;       // ... if any
    protected bit [M-1:0]          m_wait;
    protected bit [M-1:0][PB-1:0]  m_on;       // the producer dependent d waits on

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_steppable(this);
    endfunction

    function void build();
        ent = new("ent", this);
        ret = new("ret", this);
        ok = new("ok", this);
    endfunction

    virtual function void step();
        bit [IB:0]          e;
        bit [PB-1:0]        q, qp, top, pid;
        bit [DB-1:0]        did;
        bit                 eok, rok, rv, qpv, tv, gone;
        bit [N-1:0]         rq, pm, live, pv;
        bit [N-1:0][PB-1:0] prev;
        bit [M-1:0]         dm, wt;
        bit [M-1:0][PB-1:0] on;
        eok = ent.t.try_get(e);
        rok = ret.t.try_get(q);
        // Retire: unlink q.
        for (int i = 0; i < N; i++)
            rq[i] = rok && m_live[i] && q == PB'(i);
        rv = |rq;
        qp = '0;
        qpv = 1'b0;
        for (int i = 0; i < N; i++) begin
            qp = qp | (rq[i] ? m_prev[i] : PB'(0));
            qpv = qpv | (rq[i] && m_pv[i]);
        end
        for (int i = 0; i < N; i++) begin
            gone = rv && m_live[i] && m_pv[i] && m_prev[i] == q;
            prev[i] = gone ? qp : m_prev[i];
            pv[i] = gone ? qpv : m_pv[i];
        end
        gone = rv && m_tv && m_top == q;
        top = gone ? qp : m_top;
        tv = gone ? qpv : m_tv;
        live = m_live & ~rq;
        // A producer enters on top of the list.
        pid = PB'(e[IB-1:0]);
        for (int i = 0; i < N; i++)
            pm[i] = eok && !e[IB] && pid == PB'(i) && !live[i];
        for (int i = 0; i < N; i++) begin
            prev[i] = pm[i] ? top : prev[i];
            pv[i] = pm[i] ? tv : pv[i];
        end
        top = (|pm) ? pid : top;
        tv = tv || (|pm);
        // A dependent records the youngest producer at the start of the
        // cycle; a retire releases those waiting on it.
        did = DB'(e[IB-1:0]);
        for (int d = 0; d < M; d++) begin
            dm[d] = eok && e[IB] && did == DB'(d);
            on[d] = dm[d] ? m_top : m_on[d];
            wt[d] = dm[d] ? m_tv : m_wait[d];
            wt[d] = wt[d] && !(rv && on[d] == q);
        end
        m_live = live | pm;
        m_prev = prev;
        m_pv = pv;
        m_top = top;
        m_tv = tv;
        m_wait = wt;
        m_on = on;
        ok.t.set(~wt);
    endfunction
endclass
