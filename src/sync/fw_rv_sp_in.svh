// The consumer's view of an fw_rv_sig: it drives ready, and reads valid and
// data as the peer (valid reset-forced). Reading its own ready gives `cur`.
// Holder and connections as for fw_rv_sp_out. The fw_reads/fw_writes
// attributes name the field each accessor touches, for the settle weaver.
class fw_rv_sp_in #(type T = bit) extends fw_sync_port;
    fw_rv_sig #(T) sig;

    function new(fw_rv_sig #(T) sig = null, string name = "",
                 fw_component owner = null);
        super.new(name, owner, FW_SYNC_BWD, m_mk(sig, name));
        $cast(this.sig, holder());
    endfunction

    static function fw_rv_sig #(T) m_mk(fw_rv_sig #(T) sig, string name);
        if (sig == null) sig = new(name);
        return sig;
    endfunction

    // A sibling's producer end.
    function void connect(fw_rv_sp_out #(T) peer);
        m_connect(peer);
    endfunction

    // The parent's consumer end, which this end drives ready through.
    function void connect_up(fw_rv_sp_in #(T) outer);
        m_connect_up(outer);
    endfunction

    virtual protected function void m_set_holder(fw_sig_holder h);
        if (!$cast(sig, h))
            $fatal(1, "fw-hdl: %s: holder \"%s\" has another payload type", full_name(), h.name);
    endfunction

    (* fw_writes = "ready" *) function void set_ready(bit v); sig.set_ready(v); endfunction
    (* fw_reads = "ready" *)  function bit  get_ready();      return sig.get_ready(0); endfunction
    (* fw_reads = "valid" *)  function bit  get_valid();      return sig.get_valid(1); endfunction
    (* fw_reads = "data" *)   function T    get_data();       return sig.get_data(1);  endfunction
endclass
