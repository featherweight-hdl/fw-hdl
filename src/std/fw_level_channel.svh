typedef class fw_level_channel;

class fw_level_channel_set_ex #(type T = int) extends fw_export #(fw_level_set_if #(T))
        implements fw_level_set_if #(T);
    local fw_level_channel #(T) m_ch;

    function new(string name, fw_level_channel #(T) ch);
        super.new(name, ch, this);
        m_ch = ch;
    endfunction

    virtual function void set(input T t);
        m_ch.value = t;
    endfunction
endclass

class fw_level_channel_get_ex #(type T = int) extends fw_export #(fw_level_if #(T))
        implements fw_level_if #(T);
    local fw_level_channel #(T) m_ch;

    function new(string name, fw_level_channel #(T) ch);
        super.new(name, ch, this);
        m_ch = ch;
    endfunction

    virtual function T get();
        return m_ch.value;
    endfunction
endclass

// A level between two components: the writer's fw_level_set_if port sets the
// value, the reader's fw_level_if port reads it, neither waits.
//
//     fw_level_channel #(cfg_t) cfg;         // in build(): cfg = new("cfg", this);
//     regs.mode.connect(cfg.put_ex);         // regs: fw_port #(fw_level_set_if #(cfg_t))
//     core.mode.connect(cfg.get_ex);         // core: fw_port #(fw_level_if #(cfg_t))
//
// The ends are named put_ex (the writer) and get_ex (the reader), like
// fw_channel's. In RTL the channel is a wire from the writer's data pin to the
// reader's; there is no FIFO, valid or ready.
class fw_level_channel #(type T = int) extends fw_component;
    fw_level_channel_set_ex #(T) put_ex;
    fw_level_channel_get_ex #(T) get_ex;
    T value;

    function new(string name, fw_component parent);
        super.new(name, parent);
        put_ex = new("put_ex", this);
        get_ex = new("get_ex", this);
    endfunction
endclass
