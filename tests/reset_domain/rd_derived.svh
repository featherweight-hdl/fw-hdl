// Derived reset domains over a bench-local source (`hard`, so the source's
// assertion is observable to live code):
//
//   srst  = hard OR ctrl[3]                       (fw_reg_reset_domain)
//   en    = hard OR !ctrl[4]                      (active_low: an enable bit)
//   any   = srst OR other                         (fw_reset_combine, 2)
//   one   = hard                                  (fw_reset_combine, 1: pass-through)
//   chain = any OR ctrl[5]                        (reg bit over a combine)
//
// l_srst runs in `srst`; the probe watches `srst`'s waits.
class rd_derived extends fw_component;
    fw_reg_block #(32)        rf;
    fw_reg #(bit [31:0])      ctrl;
    rd_sig_reset              hard;
    rd_sig_reset              other;
    fw_reg_reset_domain #(32) srst;
    fw_reg_reset_domain #(32) en;
    fw_reset_combine          any;
    fw_reset_combine          one;
    fw_reg_reset_domain #(32) chain;
    rd_leaf                   l_srst;
    rd_probe                  probe;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        rf     = new("rf", this);
        ctrl   = new("ctrl", rf);
        hard   = new("hard", this, 1'b0);
        other  = new("other", this, 1'b0);
        srst   = new("srst", this, ctrl, 3);
        en     = new("en", this, ctrl, 4, 1'b1);
        any    = new("any", this, 2);
        one    = new("one", this, 1);
        chain  = new("chain", this, ctrl, 5);
        l_srst = new("l_srst", this);
        probe  = new("probe", this);
    endfunction

    function void connect();
        hard.clk.connect(this.clock);
        other.clk.connect(this.clock);
        srst.src.connect(hard);
        en.src.connect(hard);
        any.src[0].connect(srst);
        any.src[1].connect(other);
        one.src[0].connect(hard);
        chain.src.connect(any);
        l_srst.reset.connect(srst);
        probe.dom.connect(srst);
    endfunction
endclass
