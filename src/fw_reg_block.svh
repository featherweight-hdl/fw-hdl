
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
class fw_reg_block #(int W = 32) implements fw_reg_block_if #(W);
    protected string             m_name;
    protected int unsigned       m_stride;   // uniform byte stride = W/8
    protected int unsigned       m_next;     // next auto-assigned offset
    protected int unsigned       m_size;     // running byte span
    protected fw_reg_base  #(W)  m_regs  [int unsigned]; // owned regs, by offset
    protected fw_reg_block #(W)  m_blocks[int unsigned]; // nested sub-blocks, by base offset

    function new(string name);
        m_name = name;  m_stride = (W + 7) / 8;  m_next = 0;  m_size = 0;
    endfunction

    function string       name();   return m_name; endfunction
    virtual function int unsigned size(); return m_size; endfunction

    // Add a register. Offset auto-assigns to the running cursor (stride W/8)
    // unless given -- the user only specifies an offset for gaps / placement.
    function void add(fw_reg_base #(W) r, int offset = -1);
        int unsigned off = (offset < 0) ? m_next : offset;
        r.set_offset(off);
        m_regs[off] = r;
        bump(off + m_stride);
    endfunction

    // Add a nested block (e.g. a per-channel register file) at a base offset.
    function void add_block(fw_reg_block #(W) b, int offset = -1);
        int unsigned off = (offset < 0) ? m_next : offset;
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
    virtual function bit [W-1:0] read_val(input int unsigned a);
        fw_reg_val_if #(W) e = lookup(a);
        if (e == null) return '0;
        return e.sw_read();
    endfunction

    virtual task write_val(input int unsigned a, input bit [W-1:0] v);
        fw_reg_val_if #(W) e = lookup(a);
        if (e != null) e.write_val(v);
    endtask
endclass
