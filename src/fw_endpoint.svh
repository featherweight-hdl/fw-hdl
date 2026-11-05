// The untyped base of every port and export.
//
// fw_if_base #(T) is specialized per interface type, so code that takes "any
// endpoint" (an extern's port map, a facts declaration) takes this instead
// and names the endpoint through ep_name().
virtual class fw_endpoint;
    // The endpoint's local name. Held here rather than privately in each
    // subclass so that one endpoint can NAME another across the T boundary --
    // which is what lets the bind map say "port `out` -> export `in`" instead of
    // "port `out` -> <something>".
    protected string m_ep_name;

    function string ep_name();
        return m_ep_name;
    endfunction
endclass
