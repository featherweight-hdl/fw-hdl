typedef class fw_channel;

// The put side: an export that is its own imp, as fw_put_xtor_bridge is.
class fw_channel_put_ex #(type T = int, int DEPTH = 1) extends fw_export #(fw_put_if #(T))
        implements fw_put_if #(T);
    local fw_channel #(T, DEPTH) m_ch;

    function new(string name, fw_channel #(T, DEPTH) ch);
        super.new(name, ch, this);
        m_ch = ch;
    endfunction

    virtual task put(input T t);
        m_ch.ch_put(t);
    endtask
endclass

// The put side for an all-or-nothing step (fw_put_step_if, put_or_stall).
class fw_channel_put_step_ex #(type T = int, int DEPTH = 1)
        extends fw_export #(fw_put_step_if #(T)) implements fw_put_step_if #(T);
    local fw_channel #(T, DEPTH) m_ch;

    function new(string name, fw_channel #(T, DEPTH) ch);
        super.new(name, ch, this);
        m_ch = ch;
    endfunction

    virtual task put(input T t);
        m_ch.ch_put(t);
    endtask

    virtual function void put_or_stall(input T t);
        m_ch.ch_put_or_stall(t);
    endfunction
endclass

// Undoes one take of a step that stalled.
class fw_channel_undo #(type T = int, int DEPTH = 1) extends fw_step_undo;
    fw_channel #(T, DEPTH) ch;
    T        v;
    realtime t;

    virtual function void undo();
        ch.ch_undo(v, t);
    endfunction
endclass

// The get side.
class fw_channel_get_ex #(type T = int, int DEPTH = 1) extends fw_export #(fw_get_if #(T))
        implements fw_get_if #(T);
    local fw_channel #(T, DEPTH) m_ch;

    function new(string name, fw_channel #(T, DEPTH) ch);
        super.new(name, ch, this);
        m_ch = ch;
    endfunction

    virtual task get(output T t);
        m_ch.ch_get(t);
    endtask
endclass

// The get side for a consumer that polls (fw_get_nb_if).
class fw_channel_get_nb_ex #(type T = int, int DEPTH = 1) extends fw_export #(fw_get_nb_if #(T))
        implements fw_get_nb_if #(T);
    local fw_channel #(T, DEPTH) m_ch;

    function new(string name, fw_channel #(T, DEPTH) ch);
        super.new(name, ch, this);
        m_ch = ch;
    endfunction

    virtual task get(output T t);
        m_ch.ch_get(t);
    endtask

    virtual function bit try_get(inout T t);
        return m_ch.ch_try_get(t);
    endfunction
endclass

// A point-to-point channel between two components that both hold PORTS: a
// producer's `fw_port #(fw_put_if #(T))` and a consumer's
// `fw_port #(fw_get_if #(T))`. A port can only connect to an export, so two
// ports need this object between them:
//
//     fw_channel #(pkt_t, 2) ch;          // in build(): ch = new("ch", this);
//     prod.out.connect(ch.put_ex);        // in connect()
//     cons.in.connect(ch.get_ex);
//
// put() and get() are blocking, with no peek and no try, so a network of
// components joined by channels is a Kahn process network: each channel's
// value stream depends on neither timing nor DEPTH, unless the network
// deadlocks. A consumer that polls connects to get_nb_ex
// (fw_get_nb_if, try_get) instead, and opts out of that guarantee.
//
// An all-or-nothing step (fw_atomic_step) puts through put_step_ex
// (fw_put_step_if): put_or_stall stalls the step unless the channel had space
// at the start of the edge, counting neither values steps put during the edge
// nor values steps took during it. A value put is kept even if another output
// stalls the step, and the channel takes no more from that step until it
// commits (fw_steppable).
//
// DEPTH is how many values the channel holds:
//   * DEPTH >= 1 -- a FIFO: put() blocks while DEPTH values are waiting.
//   * DEPTH == 0 -- a rendezvous: put() returns once a get() has taken the
//     value, so a producer never runs ahead of its consumer.
// A synthesis flow maps the same DEPTH onto RTL: a ready/valid wire for 0,
// fw_rv_fifo otherwise.
//
// Per cycle, between steps (DEPTH >= 1), the model keeps fw_rv_fifo's timing
// exactly:
//   Observes  the values held at the start of the cycle. A put is accepted
//             when fewer than DEPTH were held; a step's try_get sees the
//             oldest of them.
//   Consumes  at most one put and one take a cycle, each on its own side.
//   Latency   one cycle: a value put in a cycle is offered from the next
//             (no bypass).
//   Full      a put is refused even in a cycle that takes a value (no
//             pass-through when full), so DEPTH 1 runs at half rate and full
//             rate needs DEPTH 2.
// A step may not use a DEPTH 0 channel. Its RTL is a wire, which moves a
// value in the cycle it is put, and steps at one edge do not see each
// other's puts; the model stops with an error, and so does partition.
// Timed library code (it waits on its queue); its put/get tolerate any delay.
(* fw_timed, fw_latency_insensitive *)
class fw_channel #(type T = int, int DEPTH = 1) extends fw_component;
    fw_channel_put_ex #(T, DEPTH) put_ex;
    fw_channel_put_step_ex #(T, DEPTH) put_step_ex;
    fw_channel_get_ex #(T, DEPTH) get_ex;
    fw_channel_get_nb_ex #(T, DEPTH) get_nb_ex;

    local T            m_q[$];
    // When each waiting value was put: a step does not see a value put
    // during its own edge (fw_steppable).
    local realtime     m_t[$];
    // Completed puts and gets, so a rendezvous put can wait for its own value
    // to be taken.
    local longint      m_n_put;
    local longint      m_n_get;
    // Puts and takes by steps during the latest edge, so put_or_stall sees
    // the values waiting at the start of the edge.
    local realtime     m_edge_t = -1;
    local int          m_edge_put;
    local int          m_edge_take;
    // put_step_ex took a value from a step that has not committed yet.
    local fw_step_sent m_sent = new;

    function new(string name, fw_component parent);
        super.new(name, parent);
        put_ex = new("put_ex", this);
        put_step_ex = new("put_step_ex", this);
        get_ex = new("get_ex", this);
        get_nb_ex = new("get_nb_ex", this);
    endfunction

    task ch_put(input T t);
        longint seq;
        // A rendezvous still stages one value, so that get() has something to
        // take; the put then waits for that get.
        wait (m_q.size() < ((DEPTH == 0) ? 1 : DEPTH));
        m_q.push_back(t);
        m_t.push_back($realtime);
        seq = ++m_n_put;
        if (DEPTH == 0)
            wait (m_n_get >= seq);
    endtask

    task ch_get(output T t);
        wait (m_q.size() > 0);
        t = m_q.pop_front();
        void'(m_t.pop_front());
        m_n_get++;
    endtask

    function bit ch_try_get(inout T t);
        if (DEPTH == 0 && fw_step_ctx::active)
            step_on_wire();
        if (m_q.size() == 0 || fw_step_ctx::hidden(m_t[0]))
            return 1'b0;
        if (fw_step_ctx::atomic)
            log_undo(m_q[0], m_t[0]);
        t = m_q.pop_front();
        void'(m_t.pop_front());
        m_n_get++;
        if (fw_step_ctx::active)
            edge_count(0, 1);
        return 1'b1;
    endfunction

    // From an all-or-nothing step: put t if there was space at the start of
    // the edge, else stall the step. Nothing if this step's value already
    // went, at an edge where it stalled.
    function void ch_put_or_stall(input T t);
        int held = m_q.size();
        fw_step_ctx::check_atomic(get_full_name());
        if (DEPTH == 0)
            step_on_wire();
        if (m_sent.sent)
            return;
        if (m_edge_t == $realtime)
            held += m_edge_take - m_edge_put;
        if (held >= ((DEPTH == 0) ? 1 : DEPTH)) begin
            fw_step_ctx::stall();
            return;
        end
        m_q.push_back(t);
        m_t.push_back($realtime);
        m_n_put++;
        edge_count(1, 0);
        fw_step_ctx::sent(m_sent);
    endfunction

    local function void step_on_wire();
        $fatal(1, "%s: a step cannot use a DEPTH 0 channel (a wire); use DEPTH 1 or more",
               get_full_name());
    endfunction

    local function void edge_count(int nput, int ntake);
        if (m_edge_t != $realtime) begin
            m_edge_t = $realtime;
            m_edge_put = 0;
            m_edge_take = 0;
        end
        m_edge_put += nput;
        m_edge_take += ntake;
    endfunction

    local function void log_undo(T v, realtime t);
        fw_channel_undo #(T, DEPTH) u = new;
        u.ch = this;
        u.v = v;
        u.t = t;
        fw_step_ctx::record(u);
    endfunction

    // Undo a step's take: put the value back at the head. (A step's put is
    // never undone; see ch_put_or_stall.)
    function void ch_undo(T v, realtime t);
        m_q.push_front(v);
        m_t.push_front(t);
        m_n_get--;
        m_edge_take--;
    endfunction

    // How many values are waiting (for tests and debug).
    function int size();
        return m_q.size();
    endfunction
endclass
