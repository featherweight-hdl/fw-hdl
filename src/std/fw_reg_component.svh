
// fw_reg_component -- a register block as a child component.
//
// A register block (fw_reg_block) is not a component and has no ports, so on
// its own it cannot sit in a structural tree. fw_reg_component owns one (`blk`)
// and gives it ports:
//
//   wr     a stream of software writes, {addr, data} (AW + W bits); there is
//          no read path through the tree;
//   <reg>  one fw_level_set_if #(T) port per register hardware reads, named
//          as the register property in BLK and of the register's type T.
//
// The subclass declares the level ports and ties each to its register in
// connect(), with `drive`:
//
//   class cfg_rc extends fw_reg_component #(cfg_regs);
//       fw_port #(fw_level_set_if #(cfg_t)) cfg;
//       function void build();
//           super.build();
//           cfg = new("cfg", this);
//       endfunction
//       function void connect();
//           drive(fw_reg_level #(cfg_t)::make(blk.cfg, cfg));
//       endfunction
//   endclass
//
// A level port carries the register's value: its reset value from the start
// of run(), then the value after each software write. In RTL the component is
// the generated regblock core (emit/regblock.py) under a wrapper whose level
// outputs are the hwif_out nets (fw.hdl.spl: engine `native`).
virtual class fw_reg_level_base;
    pure virtual function void update();
endclass

class fw_reg_level #(type T = bit) extends fw_reg_level_base
        implements fw_reg_wr_if #($bits(T));
    local fw_reg #(T)                     m_r;
    local fw_port #(fw_level_set_if #(T)) m_p;

    function new(fw_reg #(T) r, fw_port #(fw_level_set_if #(T)) p);
        m_r = r;
        m_p = p;
    endfunction

    static function fw_reg_level #(T) make(fw_reg #(T) r, fw_port #(fw_level_set_if #(T)) p);
        fw_reg_level #(T) l = new(r, p);
        r.add_wr(l);
        return l;
    endfunction

    virtual function void update();
        m_p.t.set(m_r.read());
    endfunction

    virtual task on_write(input bit [$bits(T)-1:0] val, input bit [$bits(T)-1:0] prev);
        update();
    endtask
endclass

class fw_reg_component #(type BLK = fw_reg_block #(32), int W = 32, int AW = 16)
        extends fw_component implements fw_runnable;
    fw_port #(fw_get_if #(bit [AW+W-1:0])) wr;
    BLK                                     blk;
    protected fw_reg_level_base             m_levels[$];

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);
    endfunction

    virtual function void build();
        wr = new("wr", this);
        blk = new("blk");
    endfunction

    // Drive a level port from a register (from connect()).
    function void drive(fw_reg_level_base l);
        m_levels.push_back(l);
    endfunction

    virtual task run();
        foreach (m_levels[i]) m_levels[i].update();
        forever begin
            bit [AW+W-1:0] w;
            wr.t.get(w);
            blk.write_val(w[AW+W-1:W], w[W-1:0]);
        end
    endtask
endclass
