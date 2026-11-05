// fw_sp_mem -- an array of WORDS values of T, held in a single-port RAM with
// a 1-cycle read. It is a member of a step class (not a component):
//
//   mem.read(a)      read word a; its data is rd() from the next step on;
//   mem.write(a, v)  write v to word a;
//   mem.rd()         the data of the latest read issued in an earlier step,
//                    held until the next read (as the RAM's output is).
//
// rd() is 0 before the first read. A word not yet written reads as 0 here
// and as unknown in a RAM, so a design writes a word before it reads it.
//
// A step makes at most one access (a read or a write): the RAM has one
// port. A second access in the same step is an error.
//
// So a value read in cycle t is used in cycle t + 1, and a value written in
// cycle t is read back by a read in cycle t + 1 or later. This is the RAM's
// own timing, so the model is cycle-exact for any binding of the array.
//
// In fw-hdl the member becomes two ports of the class's block: <mem>_req,
// valid-only {we, a, wd}, and <mem>_rd, a level. The knob `storage:` picks
// what is wired to them (a flop RAM model by default, or a RAM macro);
// every binding has this timing.
//
// A step that uses a memory cannot stall (no put_or_stall): in RTL the
// RAM access of a stalled cycle would still happen. fw-hdl reports one that
// does. The model undoes the access of a stalled step all the same.
typedef class fw_sp_mem_undo;

class fw_sp_mem #(type T = bit [7:0], int WORDS = 16);
    localparam int AW = (WORDS > 1) ? $clog2(WORDS) : 1;

    local T        m_mem[WORDS];
    local T        m_rd;        // rd() from the step after the latest read
    local T        m_rd_prev;   // rd() in the step that read
    local realtime m_rd_t = -1;
    local realtime m_acc_t = -1;

    function T rd();
        return ($realtime > m_rd_t) ? m_rd : m_rd_prev;
    endfunction

    function void read(input bit [AW-1:0] a);
        access("read");
        log_undo(0, a, m_mem[a]);
        m_rd_prev = rd();
        m_rd = (a < WORDS) ? m_mem[a] : T'(0);
        m_rd_t = $realtime;
    endfunction

    function void write(input bit [AW-1:0] a, input T v);
        access("write");
        if (a >= WORDS)
            return;
        log_undo(1, a, m_mem[a]);
        m_mem[a] = v;
    endfunction

    local function void access(string what);
        if (m_acc_t == $realtime)
            $fatal(1, "fw_sp_mem: a second access (%s) in one step; the RAM has one port",
                   what);
        m_acc_t = $realtime;
    endfunction

    local function void log_undo(bit wr, bit [AW-1:0] a, T old);
        fw_sp_mem_undo #(T, WORDS) u = new;
        u.m = this;
        u.wr = wr;
        u.a = a;
        u.old = old;
        u.rd = m_rd;
        u.rd_prev = m_rd_prev;
        u.rd_t = m_rd_t;
        fw_step_ctx::record(u);
    endfunction

    // Put back what one access of a stalled step changed.
    function void undo_access(bit wr, bit [AW-1:0] a, T old, T rd, T rd_prev,
                              realtime rd_t);
        if (wr)
            m_mem[a] = old;
        m_rd = rd;
        m_rd_prev = rd_prev;
        m_rd_t = rd_t;
        m_acc_t = -1;
    endfunction
endclass

// Undoes one access of a step that stalled.
class fw_sp_mem_undo #(type T = bit [7:0], int WORDS = 16) extends fw_step_undo;
    fw_sp_mem #(T, WORDS) m;
    bit                   wr;
    bit [31:0]            a;
    T                     old;
    T                     rd;
    T                     rd_prev;
    realtime              rd_t;

    virtual function void undo();
        m.undo_access(wr, a, old, rd, rd_prev, rd_t);
    endfunction
endclass
