
// fw_reg_set -- a register watch-set that records WHICH register moved.
//
// Hardware (a sequential process) often wants to sleep until ANY of a set of
// registers -- gathered from anywhere in the hierarchy, e.g. all 31 channel CSRs
// -- changes, and be told WHICH one. Members push their identity on change
// (reg.signal() -> notify_from), so the waiter learns the cause; that is what
// distinguishes this from the source-agnostic fw_event_set (which only reports
// THAT something fired). A consumer that does not need the cause -- and may also
// wait on non-register sources -- uses fw_event_set instead.
//
// The set is flat over whatever registers are add()ed, so it spans sub-blocks
// freely. One backing event, no per-register process. A burst of same-delta
// updates may wake a waiter more than once, which a re-arbitrate loop tolerates.
class fw_reg_set #(int W = 32);
    protected fw_reg_base #(W) m_regs[$];
    protected event            m_any;
    protected fw_reg_base #(W) m_last;     // which register changed

    function void add(fw_reg_base #(W) r);
        m_regs.push_back(r);
        r.subscribe(this);                 // reg.signal() -> this.notify_from()
    endfunction

    // called by a member register on any value change: record which, then wake
    function void notify_from(fw_reg_base #(W) r);  m_last = r;  -> m_any;  endfunction

    // block until ANY member changes; hand back which one
    task wait_change(output fw_reg_base #(W) which);
        @(m_any);
        which = m_last;
    endtask
endclass
