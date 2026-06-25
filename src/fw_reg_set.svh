
// fw_reg_set -- a hierarchical watch-set for wait-for-change.
//
// Hardware (a sequential process) often wants to sleep until ANY of a set of
// registers -- gathered from anywhere in the hierarchy, e.g. all 31 channel CSRs
// -- changes, and be told WHICH one. That is how the design uses change
// notification: the engine's arbiter wakes, learns which channel's CSR moved,
// and re-evaluates.
//
// The set is flat over whatever registers are add()ed, so it spans sub-blocks
// freely -- that IS the hierarchy support. One SV event backs the whole set: no
// per-register process, no spinning. A burst of same-delta updates may wake a
// waiter more than once, which a re-arbitrate loop tolerates.
class fw_reg_set #(int W = 32);
    protected fw_reg_base #(W) m_regs[$];
    protected event            m_any;
    protected fw_reg_base #(W) m_last;     // which register changed

    function void add(fw_reg_base #(W) r);
        m_regs.push_back(r);
        r.subscribe(this);                 // reg.signal() -> this.notify()
    endfunction

    // called by a member register on any value change
    function void notify(fw_reg_base #(W) r);  m_last = r; -> m_any; endfunction

    // block until ANY member changes; hand back which one
    task wait_change(output fw_reg_base #(W) which);
        @(m_any);
        which = m_last;
    endtask
endclass
