// fw_resource -- a hazard lock, after PDL (docs/methodology/timing.md,
// resources): it orders accesses to state the compiler can't see, such as
// memory behind a port, when a schedule overlaps iterations.
//
//   reserve(key, rw)  record the access, in program order (a function);
//   block(key)        wait until the access is safe (a task);
//   acquire(key, rw)  reserve, then block;
//   free(key)         release: commit; write releases go in the order
//                     reserved. (PDL's name, release, is an SV keyword.)
//
// key selects the part of the state (an address or index); a whole resource
// uses one key (the default, 0). Every path must take each reservation
// through reserve -> block -> access -> free. A port whose calls are the
// access names the resource with (* fw_guard="<field>" *); a call through it
// outside a block .. free is an error.
//
// This is the sequential implementation: it takes no time, and only checks
// that the operations come in order ($error on misuse). Erasing the calls
// gives the same behavior. The synthesis flow reads the calls as lock
// operations, checks them on every path, and erases them when the schedule
// doesn't overlap iterations.
typedef enum bit {FW_READ = 1'b0, FW_WRITE = 1'b1} fw_rw_e;

(* fw_latency_insensitive *)
class fw_resource #(type KEY = bit);
    protected string  m_name;
    protected KEY     m_key[$];
    protected fw_rw_e m_rw[$];
    protected bit     m_blk[$];

    function new(string name = "fw_resource");
        m_name = name;
    endfunction

    function void reserve(KEY key = 0, fw_rw_e rw = FW_WRITE);
        if (find(key) >= 0)
            $error("%s: reserve(%0d): already reserved", m_name, key);
        m_key.push_back(key);
        m_rw.push_back(rw);
        m_blk.push_back(1'b0);
    endfunction

    task block(KEY key = 0);
        int i = find(key);
        if (i < 0)
            $error("%s: block(%0d) without reserve", m_name, key);
        else if (m_blk[i])
            $error("%s: block(%0d): already blocked", m_name, key);
        else
            m_blk[i] = 1'b1;
    endtask

    task acquire(KEY key = 0, fw_rw_e rw = FW_WRITE);
        reserve(key, rw);
        block(key);
    endtask

    function void free(KEY key = 0);
        int i = find(key);
        if (i < 0) begin
            $error("%s: free(%0d) without reserve", m_name, key);
            return;
        end
        if (!m_blk[i])
            $error("%s: free(%0d) before block", m_name, key);
        if (m_rw[i] == FW_WRITE)
            for (int j = 0; j < i; j++)
                if (m_rw[j] == FW_WRITE)
                    $error("%s: free(%0d): write releases go in program order (%0d first)",
                           m_name, key, m_key[j]);
        m_key.delete(i);
        m_rw.delete(i);
        m_blk.delete(i);
    endfunction

    // Whether key is reserved and blocked (an access may proceed).
    function bit held(KEY key = 0);
        int i = find(key);
        return i >= 0 && m_blk[i];
    endfunction

    protected function int find(KEY key);
        foreach (m_key[i])
            if (m_key[i] == key)
                return i;
        return -1;
    endfunction
endclass
