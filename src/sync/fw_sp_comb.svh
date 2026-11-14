// The comb fields one class declares on its port members with
// `(* fw_sp_comb = "ar.*,w.valid" *)`. The fw_sp_comb weaver
// (python/fw/hdl/weave/sp_comb.py) generates one subclass per class
// (specialization) whose apply() $casts a component to that class and calls
// set_comb on each declaring member, and registers it from `<pkg>_woven`.
// fw_sync_kernel::freeze_tree() applies them to the whole tree before it
// freezes the holders, so the setting is fixed at the end of build.
virtual class fw_sp_comb;
    static fw_sp_comb m_all[$];

    static function void add(fw_sp_comb a);
        m_all.push_back(a);
    endfunction

    // 1 if c is an instance of the class (its set_comb calls were made).
    pure virtual function bit apply(fw_component c);

    static function void apply_tree(fw_component c);
        fw_component kids[$];
        foreach (m_all[i]) void'(m_all[i].apply(c));
        c.get_children(kids);
        foreach (kids[i]) apply_tree(kids[i]);
    endfunction
endclass
