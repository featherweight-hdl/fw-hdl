
// fw_reg_base -- the (untyped) register state machine.
//
// A register IS a piece of hardware-owned state plus a small behavioral
// contract. Two actors touch the same state, mirroring SystemRDL's sw/hw split:
//
//   Actor      Reads with                Writes with            Masked by
//   --------   -----------------------   --------------------   ---------
//   Hardware   read_val (canonical)      update_val             hw_wmask
//   Software   sw_read (via bus)         write_val (via bus)    sw_wmask
//
// Single source of truth: a register has exactly one canonical value -- whatever
// the read-provider hook (fw_reg_rd_if) returns when attached, else the stored
// value. read_val() routes through the provider, so hardware never observes a
// different value than software. read-to-clear (rclr) is a side effect of a
// genuine software bus read ONLY (sw_read), never of the pure value function.
//
// The typed projection (named-field access over a packed struct) lives in the
// fw_reg #(T) subclass; this base works purely in W-wide values so a group can
// hold heterogeneous registers as fw_reg_val_if #(W).

typedef class fw_reg_set;   // forward: register <-> watch-set are mutually referential
typedef class fw_reg_block; // forward: a register self-adds to its parent group

virtual class fw_reg_base #(int W = 32) implements fw_reg_val_if #(W), fw_awaitable_if;
    protected string         m_name;
    protected int unsigned   m_offset;     // assigned when added to a group
    protected bit [W-1:0]    m_val;        // hardware-owned state
    protected bit [W-1:0]    m_reset;
    // ---- access contract ----------------------------------------------------
    protected bit [W-1:0]    m_sw_wmask;   // bits SOFTWARE may write
    protected bit [W-1:0]    m_hw_wmask;   // bits HARDWARE may write
    protected bit [W-1:0]    m_rclr_mask;  // bits cleared as a side effect of a sw read
    // ---- hardware hooks ------------------------------------------------------
    protected fw_reg_rd_if #(W) m_rd;      // read provider (optional, single)
    protected fw_reg_wr_if #(W) m_wr[$];   // write observers (zero or more)
    // ---- change notification --------------------------------------------------
    protected event             m_change;    // fired on any value change
    protected fw_reg_set #(W)   m_sets[$];   // register watch-sets (track which)
    protected fw_event_set      m_mons[$];   // monitors this register produces into

    // A register always belongs to a group: `parent` is mandatory and the register
    // adds itself (mirroring how an fw_component registers with its parent), so a
    // register file is declared as just `r = new("r", this)` -- no separate add()
    // call. `offset` defaults to the group's running cursor (uniform stride); pass
    // an explicit byte offset only to leave a gap or force placement.
    function new(string name,
                 fw_reg_block #(W) parent,
                 int         offset    = -1,
                 bit [W-1:0] reset     = '0,
                 bit [W-1:0] sw_wmask  = '1,
                 bit [W-1:0] hw_wmask  = '0,
                 bit [W-1:0] rclr_mask = '0);
        m_name = name;  m_reset = reset;  m_val = reset;
        m_sw_wmask = sw_wmask;  m_hw_wmask = hw_wmask;  m_rclr_mask = rclr_mask;
        parent.add(this, offset);   // self-register (at the cursor, or `offset`)
    endfunction

    function string       name();              return m_name;   endfunction
    function void         reset();             m_val = m_reset; signal(); endfunction
    function void         set_offset(int unsigned o); m_offset = o;       endfunction
    function int unsigned offset();            return m_offset;           endfunction
    function void         set_rd(fw_reg_rd_if #(W) rd); m_rd = rd;        endfunction
    function void         add_wr(fw_reg_wr_if #(W) wr); m_wr.push_back(wr); endfunction
    function void         subscribe(fw_reg_set #(W) s); m_sets.push_back(s); endfunction
    // fw_awaitable_if: this register IS an event source -- produce its "event
    // occurred" into monitor `s` (push). signal() then notifies s on every change,
    // so a consumer waits on a set spanning this register and other sources.
    virtual function void produce_to(fw_event_set s);  m_mons.push_back(s);  endfunction

    // any value change: fire the change event, notify register watch-sets, and
    // produce into subscribed monitors
    protected function void signal();
        -> m_change;
        foreach (m_sets[i]) m_sets[i].notify_from(this);   // register watch-set (which)
        foreach (m_mons[i]) m_mons[i].notify();            // fw_event_set monitors (push)
    endfunction

    // --- CANONICAL value: the single source of truth. The read provider (if
    //     attached) supplies it from live hardware state; otherwise the stored
    //     value. Pure: NO side effects.
    virtual function bit [W-1:0] read_val();
        return (m_rd != null) ? m_rd.on_read(m_val) : m_val;
    endfunction

    // --- SOFTWARE bus read: sample the canonical value, then apply the
    //     read-to-clear side effect. Only a genuine software bus access lands
    //     here -- a hardware read_val()/read() peek never clears.
    virtual function bit [W-1:0] sw_read();
        bit [W-1:0] v = read_val();
        if (|m_rclr_mask) begin
            m_val = m_val & ~m_rclr_mask;
            signal();
        end
        return v;
    endfunction

    // --- SOFTWARE write: masked by sw_wmask, then notify write observers.
    virtual task write_val(input bit [W-1:0] v);
        bit [W-1:0] prev = m_val;
        m_val = (m_val & ~m_sw_wmask) | (v & m_sw_wmask);
        if (m_val !== prev) signal();
        foreach (m_wr[i]) m_wr[i].on_write(m_val, prev);
    endtask

    // --- HARDWARE update: masked by hw_wmask (intersected with the inline mask).
    //     Hardware owns these bits, so on sw/hw overlap the hardware update is
    //     authoritative (SystemRDL hw precedence). Does NOT fire write observers.
    virtual task update_val(input bit [W-1:0] v, input bit [W-1:0] mask = '1);
        bit [W-1:0] eff  = m_hw_wmask & mask;
        bit [W-1:0] prev = m_val;
        m_val = (m_val & ~eff) | (v & eff);
        if (m_val !== prev) signal();
    endtask
endclass
