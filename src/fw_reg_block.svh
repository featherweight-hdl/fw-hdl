
// fw_reg_block -- a register group / register file.
//
// Holds registers (and nested sub-blocks) at byte offsets and decodes a bus
// access to the right entry. Offsets auto-assign at the uniform stride W/8; the
// user only specifies an offset for gaps or non-default placement. Nesting a
// sub-block (e.g. a per-channel register file) is how arrays of identical banks
// are built. Decode is registers-first, then recurse into sub-blocks.
//
// This is the bus-facing face of a group: it implements fw_reg_block_if #(W), so
// a bus adapter can provide it as an fw_export and bridge it to any bus protocol.
class fw_reg_block #(int W = 32)
        implements fw_reg_block_if #(W), fw_dbg_contextual;
    protected string             m_name;
    protected int unsigned       m_stride;   // uniform byte stride = W/8
    protected int unsigned       m_next;     // next auto-assigned offset
    protected int unsigned       m_size;     // running byte span
    protected fw_reg_base  #(W)  m_regs  [int unsigned]; // owned regs, by offset
    protected fw_reg_block #(W)  m_blocks[int unsigned]; // nested sub-blocks, by base offset
    // ---- observability ---------------------------------------------------------
    protected fw_dbg_listener_if m_dbg;
    protected int unsigned       m_sid_decode;
    protected int unsigned       m_sid_miss;
    // My enclosing block, set by add_block(). Non-null means CONTAINMENT decides
    // my context, not whoever happened to construct me -- see set_dbg_context().
    protected fw_reg_block #(W)  m_parent_blk;

    // `parent` is an OVERRIDE, not a requirement.
    //
    // A block constructed during elaboration adopts the component that is
    // building it, the same way a component adopts its parent's `clock` and
    // `dbg` without being told. That is deliberate: the previous design took an
    // optional parent, and an optional argument whose omission costs you nothing
    // visible -- the registers still work, they just stop being observable -- is
    // an argument that gets omitted. It was, in this very tree: `wb_dma_rf` built
    // its register file without one and the whole of D-3 was inert in the DMA
    // model until someone went looking.
    //
    // Pass `parent` explicitly only to put a block in a DIFFERENT context than
    // its builder -- carving a per-channel context, say -- or when a block is
    // created outside elaboration, where there is no ambient owner to adopt and
    // guessing would be worse than silence.
    function new(string name, fw_component parent = null);
        fw_component owner = (parent != null) ? parent : fw_component::dbg_ambient();
        m_name = name;  m_stride = (W + 7) / 8;  m_next = 0;  m_size = 0;
        `fw_dbg_site_inst(m_sid_decode, {name, ".decode"},      FW_DBG_DECISION, FW_L_DETAIL)
        `fw_dbg_site_inst(m_sid_miss,   {name, ".decode_miss"}, FW_DBG_NOTICE,   FW_L_VITAL)
        if (owner != null) begin
            // A block that is later NESTED registers here too, but that claim is
            // then overridden -- see set_dbg_context(). Containment wins.
            owner.add_contextual(this);
`ifndef FW_TRACE_OFF
        end else begin
            // No owner and no ambient: this block will be silent. Recorded in
            // the catalog (which is unparameterized, so one list spans every
            // width) so the facility can SAY so instead of leaving someone to
            // wonder why a register file emits nothing.
            fw_dbg_catalog::note_uncontexted(name);
`endif
        end
    endfunction

    // fw_dbg_contextual: take the context and push it through the whole subtree.
    // Registers added AFTER this inherit at add() time, so the order in which a
    // register file is built does not matter.
    //
    // CONTAINMENT IS AUTHORITATIVE. A nested block ignores a context offered by
    // anyone but its enclosing block, because a register map is one artifact
    // with one root: a bank at 0x20 belongs to the map, whatever object happened
    // to call `new` on it. Without this rule a block reached both ways -- pushed
    // by the component that constructed it AND by the block that contains it --
    // resolves by registration order, which is not a decision anyone made.
    virtual function void set_dbg_context(fw_dbg_listener_if l);
        if (m_parent_blk != null) return;    // my context comes from my container
        apply_dbg_context(l);
    endfunction

    // The containment path: unconditional, used by add_block() on the way down.
    protected function void apply_dbg_context(fw_dbg_listener_if l);
        m_dbg = l;
        foreach (m_regs[o])   m_regs[o].set_dbg_context(l);
        foreach (m_blocks[o]) m_blocks[o].apply_dbg_context(l);
    endfunction

    function string       name();   return m_name; endfunction
    virtual function int unsigned size(); return m_size; endfunction

    // Add a register. Offset auto-assigns to the running cursor (stride W/8)
    // unless given -- the user only specifies an offset for gaps / placement.
    function void add(fw_reg_base #(W) r, int offset = -1);
        int unsigned off = (offset < 0) ? m_next : offset;
        r.set_offset(off);
        r.set_dbg_context(m_dbg);
        m_regs[off] = r;
        bump(off + m_stride);
    endfunction

    // Add a nested block (e.g. a per-channel register file) at a base offset.
    function void add_block(fw_reg_block #(W) b, int offset = -1);
        int unsigned off = (offset < 0) ? m_next : offset;
        // Claim containment BEFORE handing the context down: from here on this
        // block is the only thing that may set b's context.
        b.m_parent_blk = this;
`ifndef FW_TRACE_OFF
        // b is no longer a root, so it can no longer be a context-less root --
        // retract any note made when it was constructed.
        fw_dbg_catalog::clear_uncontexted(b.name());
`endif
        b.apply_dbg_context(m_dbg);
        m_blocks[off] = b;
        bump(off + b.size());
    endfunction

    protected function void bump(int unsigned end_off);
        m_next = end_off;
        if (end_off > m_size) m_size = end_off;
    endfunction

    // --- offset decode: registers first, then recurse into sub-blocks ---------
    function fw_reg_val_if #(W) lookup(input int unsigned a);
        if (m_regs.exists(a)) return m_regs[a];
        foreach (m_blocks[base]) begin
            if (a >= base && a < base + m_blocks[base].size())
                return m_blocks[base].lookup(a - base);
        end
        return null;
    endfunction

    // software bus read: routes to the register's sw_read() so read-to-clear
    // fires (a hardware peek would call read_val() instead). Unmapped -> 0.
    // A bus access is the one thing the registers themselves cannot report: a
    // READ leaves no state change, and an access to an unmapped offset touches
    // no register at all. So the decode is where those two get recorded.
    //
    // The DECISION carries a winner and no candidate list. That is deliberate:
    // an address decode has no rejected candidates worth enumerating, and
    // walking every register per access would cost far more than the event is
    // worth.
    virtual function bit [W-1:0] read_val(input int unsigned a);
        fw_reg_val_if #(W) e = lookup(a);
        if (e == null) begin
            `fw_ev_notice_at(m_dbg, FW_SEV_WARN, m_sid_miss)
                `fw_field_hex("addr", a)
                `fw_field_as("write", 0)
            `fw_ev_end
            return '0;
        end
        read_val = e.sw_read();
        `fw_ev_decision_at(m_dbg, m_sid_decode)
            `fw_dec_winner(a)
            `fw_field_hex("addr", a)
            `fw_field_hex("data", read_val)
            `fw_field_as("write", 0)
        `fw_ev_end
    endfunction

    virtual task write_val(input int unsigned a, input bit [W-1:0] v);
        fw_reg_val_if #(W) e = lookup(a);
        if (e == null) begin
            `fw_ev_notice_at(m_dbg, FW_SEV_WARN, m_sid_miss)
                `fw_field_hex("addr", a)
                `fw_field_as("write", 1)
            `fw_ev_end
            return;
        end
        `fw_ev_decision_at(m_dbg, m_sid_decode)
            `fw_dec_winner(a)
            `fw_field_hex("addr", a)
            `fw_field_hex("data", v)
            `fw_field_as("write", 1)
        `fw_ev_end
        e.write_val(v);
    endtask
endclass
