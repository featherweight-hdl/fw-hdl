typedef class fw_valid_channel;

// The put side of a valid-only channel: a function, so the producer never waits.
class fw_valid_channel_put_ex #(type T = int, int DEPTH = 1)
        extends fw_export #(fw_valid_put_if #(T)) implements fw_valid_put_if #(T);
    local fw_valid_channel #(T, DEPTH) m_ch;

    function new(string name, fw_valid_channel #(T, DEPTH) ch);
        super.new(name, ch, this);
        m_ch = ch;
    endfunction

    virtual function void put(input T t);
        m_ch.ch_put(t);
    endfunction
endclass

class fw_valid_channel_get_ex #(type T = int, int DEPTH = 1) extends fw_export #(fw_get_if #(T))
        implements fw_get_if #(T);
    local fw_valid_channel #(T, DEPTH) m_ch;

    function new(string name, fw_valid_channel #(T, DEPTH) ch);
        super.new(name, ch, this);
        m_ch = ch;
    endfunction

    virtual task get(output T t);
        m_ch.ch_get(t);
    endtask
endclass

// The get side for a consumer that polls (fw_get_nb_if), such as a step.
class fw_valid_channel_get_nb_ex #(type T = int, int DEPTH = 1)
        extends fw_export #(fw_get_nb_if #(T)) implements fw_get_nb_if #(T);
    local fw_valid_channel #(T, DEPTH) m_ch;

    function new(string name, fw_valid_channel #(T, DEPTH) ch);
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

// Undoes one take or put of a step that stalled.
class fw_valid_channel_undo #(type T = int, int DEPTH = 1) extends fw_step_undo;
    fw_valid_channel #(T, DEPTH) ch;
    bit      take;
    T        v;
    realtime t;

    virtual function void undo();
        ch.ch_undo(take, v, t);
    endfunction
endclass

// A channel whose producer never waits (fw_valid_put_if) and whose consumer
// gets with an ordinary blocking get:
//
//     fw_valid_channel #(flit_t, 4) link;    // in build(): link = new("link", this);
//     tx.out.connect(link.put_ex);           // tx: fw_port #(fw_valid_put_if #(flit_t))
//     rx.in.connect(link.get_ex);            // rx: fw_port #(fw_get_if #(flit_t))
//
// DEPTH is the receiver's buffer, which the producer's credits must not
// exceed. A put while DEPTH values wait is a credit violation: it is reported
// with $error and the value is kept, so the stream stays visible. In RTL the
// channel is a ready/valid FIFO whose producer side has no ready pin; a checker
// asserts the FIFO is never full when valid is raised. DEPTH == 0 is a wire:
// the consumer must take each value in the cycle it arrives.
//
// Between steps (fw_steppable) a put is seen from the next edge, and a step's
// put counts the values waiting at the start of its edge, as the RTL FIFO
// does. So a producer that puts every cycle needs DEPTH >= 2, and a wire
// (DEPTH == 0) cannot join two steps.
class fw_valid_channel #(type T = int, int DEPTH = 1) extends fw_component;
    fw_valid_channel_put_ex #(T, DEPTH) put_ex;
    fw_valid_channel_get_ex #(T, DEPTH) get_ex;
    fw_valid_channel_get_nb_ex #(T, DEPTH) get_nb_ex;

    local T   m_q[$];
    // When each waiting value was put (fw_channel's m_t).
    local realtime m_t[$];
    // Values steps took during the latest edge, and when: a step's put sees
    // the space there was at the start of its edge (fw_steppable).
    local realtime m_pop_t = -1;
    local int      m_npop;
    int       n_violations;

    function new(string name, fw_component parent);
        super.new(name, parent);
        put_ex = new("put_ex", this);
        get_ex = new("get_ex", this);
        get_nb_ex = new("get_nb_ex", this);
    endfunction

    function void ch_put(input T t);
        int held = m_q.size();
        if (fw_step_ctx::active && m_pop_t == $realtime)
            held += m_npop;
        if (held >= ((DEPTH == 0) ? 1 : DEPTH)) begin
            n_violations++;
            $error("fw_valid_channel %s: put while full (%0d waiting): a credit violation",
                   get_full_name(), m_q.size());
        end
        m_q.push_back(t);
        m_t.push_back($realtime);
        if (fw_step_ctx::atomic)
            log_undo(1'b0, t, $realtime);
    endfunction

    task ch_get(output T t);
        wait (m_q.size() > 0);
        t = m_q.pop_front();
        void'(m_t.pop_front());
    endtask

    function bit ch_try_get(inout T t);
        if (m_q.size() == 0 || fw_step_ctx::hidden(m_t[0]))
            return 1'b0;
        if (fw_step_ctx::atomic)
            log_undo(1'b1, m_q[0], m_t[0]);
        t = m_q.pop_front();
        void'(m_t.pop_front());
        if (fw_step_ctx::active) begin
            if (m_pop_t != $realtime)
                m_npop = 0;
            m_pop_t = $realtime;
            m_npop++;
        end
        return 1'b1;
    endfunction

    local function void log_undo(bit take, T v, realtime t);
        fw_valid_channel_undo #(T, DEPTH) u = new;
        u.ch = this;
        u.take = take;
        u.v = v;
        u.t = t;
        fw_step_ctx::record(u);
    endfunction

    // Undo a step's take (put the value back at the head) or put (drop the
    // newest value).
    function void ch_undo(bit take, T v, realtime t);
        if (take) begin
            m_q.push_front(v);
            m_t.push_front(t);
            m_npop--;
        end else begin
            void'(m_q.pop_back());
            void'(m_t.pop_back());
        end
    endfunction

    function int size();
        return m_q.size();
    endfunction
endclass
