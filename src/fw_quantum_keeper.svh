
// ----------------------------------------------------------------------------
// TLM 2.0-style quantum keeper -- temporal decoupling for loosely-timed models.
//
// A DATA SOURCE (e.g. a memory model) accounts each access's data-availability
// delay into the keeper's local offset; the keeper advances GLOBAL sim time (a
// `#` yield) only when that offset crosses the quantum. So a consumer runs many
// accesses AHEAD of global time within one quantum, paying one scheduler yield
// per quantum instead of one per access -- the standard loosely-timed speedup.
//
// Timing therefore lives entirely in the data-availability delays this batches:
// the consumer (e.g. the DMA engine) never advances time itself; it just calls
// access(), and the source's delay -- accumulated here -- is what paces it. The
// owning data path runs ahead of global time by up to `quantum`; sync() flushes
// it (a synchronization point). SIM-ONLY (no RTL analog).
// ----------------------------------------------------------------------------
class fw_quantum_keeper;
    // Shared default quantum; per-instance override via the ctor / set_quantum.
    static realtime s_quantum = 1us;
    local realtime  m_quantum;
    local realtime  m_offset = 0;

    function new(realtime quantum = 0);
        m_quantum = (quantum > 0) ? quantum : s_quantum;
    endfunction

    function void set_quantum(realtime q); m_quantum = q; endfunction

    // Account a data-availability delay. Yields global time ONLY when the quantum
    // is crossed -- the common case is a plain add (no scheduler event).
    task account(realtime t);
        m_offset += t;
        if (m_offset >= m_quantum) sync();
    endtask

    // Flush the accumulated local offset to global sim time (a sync point). Call
    // this where the model's local time must become globally visible.
    task sync();
        if (m_offset > 0) begin
            #(m_offset);
            m_offset = 0;
        end
    endtask

    function realtime offset(); return m_offset; endfunction
endclass
