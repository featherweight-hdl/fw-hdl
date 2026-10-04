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
// deadlocks (xls-phase2.md §4). A consumer that polls connects to get_nb_ex
// (fw_get_nb_if, try_get) instead, and opts out of that guarantee.
//
// DEPTH is how many values the channel holds:
//   * DEPTH >= 1 -- a FIFO: put() blocks while DEPTH values are waiting.
//   * DEPTH == 0 -- a rendezvous: put() returns once a get() has taken the
//     value, so a producer never runs ahead of its consumer.
// A synthesis flow maps the same DEPTH onto RTL: a ready/valid wire for 0, a
// ready/valid FIFO otherwise.
class fw_channel #(type T = int, int DEPTH = 1) extends fw_component;
    fw_channel_put_ex #(T, DEPTH) put_ex;
    fw_channel_get_ex #(T, DEPTH) get_ex;
    fw_channel_get_nb_ex #(T, DEPTH) get_nb_ex;

    local T            m_q[$];
    // Completed puts and gets, so a rendezvous put can wait for its own value
    // to be taken.
    local longint      m_n_put;
    local longint      m_n_get;

    function new(string name, fw_component parent);
        super.new(name, parent);
        put_ex = new("put_ex", this);
        get_ex = new("get_ex", this);
        get_nb_ex = new("get_nb_ex", this);
    endfunction

    task ch_put(input T t);
        longint seq;
        // A rendezvous still stages one value, so that get() has something to
        // take; the put then waits for that get.
        wait (m_q.size() < ((DEPTH == 0) ? 1 : DEPTH));
        m_q.push_back(t);
        seq = ++m_n_put;
        if (DEPTH == 0)
            wait (m_n_get >= seq);
    endtask

    task ch_get(output T t);
        wait (m_q.size() > 0);
        t = m_q.pop_front();
        m_n_get++;
    endtask

    function bit ch_try_get(inout T t);
        if (m_q.size() == 0)
            return 1'b0;
        t = m_q.pop_front();
        m_n_get++;
        return 1'b1;
    endfunction

    // How many values are waiting (for tests and debug).
    function int size();
        return m_q.size();
    endfunction
endclass
