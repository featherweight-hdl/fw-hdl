typedef class fw_rv_sp_in;

// The producer's view of an fw_rv_sig: it drives valid and data, and reads
// ready as the peer (reset-forced). Reading its own valid/data gives `cur`.
// With no holder given it makes its own, named after the port; connect()
// and connect_up() then share one holder across the ends (fw_sync_port).
class fw_rv_sp_out #(type T = bit) extends fw_sync_port;
    fw_rv_sig #(T) sig;

    function new(fw_rv_sig #(T) sig = null, string name = "",
                 fw_component owner = null);
        super.new(name, owner, FW_SYNC_FWD, m_mk(sig, name));
        $cast(this.sig, holder());
    endfunction

    static function fw_rv_sig #(T) m_mk(fw_rv_sig #(T) sig, string name);
        if (sig == null) sig = new(name);
        return sig;
    endfunction

    // A sibling's consumer end.
    function void connect(fw_rv_sp_in #(T) peer);
        m_connect(peer);
    endfunction

    // The parent's producer end, which this end drives through.
    function void connect_up(fw_rv_sp_out #(T) outer);
        m_connect_up(outer);
    endfunction

    virtual protected function void m_set_holder(fw_sig_holder h);
        if (!$cast(sig, h))
            $fatal(1, "fw-hdl: %s: holder \"%s\" has another payload type", full_name(), h.name);
    endfunction

    (* fw_writes = "valid" *) function void set_valid(bit v); sig.set_valid(v); endfunction
    (* fw_writes = "data" *)  function void set_data(T v);    sig.set_data(v);  endfunction
    (* fw_reads = "valid" *)  function bit  get_valid();      return sig.get_valid(0); endfunction
    (* fw_reads = "data" *)   function T    get_data();       return sig.get_data(0);  endfunction
    (* fw_reads = "ready" *)  function bit  get_ready();      return sig.get_ready(1); endfunction
endclass
