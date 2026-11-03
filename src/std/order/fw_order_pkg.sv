// fw_order_pkg: requirement contracts as executable checkers.
//
// Function is defined by contracts at observable points, not by cycle
// behaviour: two runs are the same function when their streams are equal up to
// the reorderings the contract allows. This package checks those contracts.
// It has no imports, so the same checker runs on a class model and on a
// pin-level monitor of generated RTL.
//
//   fw_order_rule   which later items may pass which earlier ones: never, any
//                   item of another key (per_key), or by item class
//                   (allow_pass); and which ordered pairs must also be in
//                   strictly later cycles (strict_after)
//   fw_order_check  items enter (enter) and leave (leave); reports reordering,
//                   unknown, duplicate or corrupted items, same-cycle
//                   violations, and (finish) items that never left
//   fw_lifetime     allocate/free/use of ids: double allocate, bad free, use
//                   after free, over max_live, and leaks at finish
//   fw_dep_check    a dependent records the youngest older producer still
//                   live when it enters; it must not be released before that
//                   producer retires (sticky: once retired, satisfied)
//   fw_trace        writes one JSON line per event, for the Python canonical
//                   comparison (fw.hdl.verif.canon)
//
// Same-cycle order: items that enter in one cycle are ordered by call order.
// A caller that wants "accepted in the same cycle counts as earlier" calls
// enter() for that point first.
//
// Errors are counted per kind, kept as text (first_error / log), and printed
// with the prefix "FW_CONTRACT" unless quiet is set.
package fw_order_pkg;

    typedef enum int {
        FW_E_REORDER,       // a later item left before an earlier one it may not pass
        FW_E_UNKNOWN,       // an item left that never entered
        FW_E_DUPLICATE,     // an item entered or left twice
        FW_E_DATA,          // an item left with other data than it entered with
        FW_E_LOST,          // finish(): an item entered and never left
        FW_E_SAME_CYCLE,    // a strict_after pair left in the same cycle
        FW_E_DOUBLE_ALLOC,  // fw_lifetime: allocate of a live id
        FW_E_BAD_FREE,      // fw_lifetime: free of an id that is not live
        FW_E_USE_DEAD,      // fw_lifetime: use of an id that is not live
        FW_E_MAX_LIVE,      // fw_lifetime: more than max_live ids live
        FW_E_LEAK,          // fw_lifetime finish(): ids still live
        FW_E_DEP_EARLY,     // fw_dep_check: released before its producer retired
        FW_E_NKINDS
    } fw_contract_err_e;

    // Shared reporting.
    virtual class fw_contract;
        string      name;
        bit         quiet;
        int         n_errors;
        int         n_kind[FW_E_NKINDS];
        string      first_error;
        string      log[$];

        function new(string name);
            this.name = name;
        endfunction

        function void error(fw_contract_err_e kind, string msg);
            string s = $sformatf("%s: %s: %s", name, kind.name(), msg);
            if (n_errors == 0)
                first_error = s;
            n_errors++;
            n_kind[kind]++;
            log.push_back(s);
            if (!quiet)
                $display("FW_CONTRACT %s", s);
        endfunction

        function int count(fw_contract_err_e kind);
            return n_kind[kind];
        endfunction
    endclass

    // Which reorderings a stream may show.
    class fw_order_rule;
        // Items with different keys never constrain each other.
        bit per_key;
        // allow_pass[{earlier class, later class}]: a later item of the second
        // class may leave before an earlier one of the first.
        bit allow_pass[longint];
        // strict_after[{earlier class, later class}]: such an ordered pair must
        // also leave in strictly later cycles (same cycle is a violation).
        bit strict_after[longint];

        static function longint pair(int earlier, int later);
            return (longint'(earlier) << 32) | longint'(unsigned'(later));
        endfunction

        // Total order: nothing passes anything.
        static function fw_order_rule in_order();
            fw_order_rule r = new;
            return r;
        endfunction

        // Order kept within a key only.
        static function fw_order_rule in_order_per_key();
            fw_order_rule r = new;
            r.per_key = 1;
            return r;
        endfunction

        function void set_pass(int earlier, int later, bit ok = 1);
            allow_pass[pair(earlier, later)] = ok;
        endfunction

        function void set_strict(int earlier, int later, bit on = 1);
            strict_after[pair(earlier, later)] = on;
        endfunction

        // Does an earlier item (key ek, class ec) bind a later one (lk, lc)?
        function bit binds(longint ek, int ec, longint lk, int lc);
            if (per_key && ek != lk)
                return 0;
            if (allow_pass.exists(pair(ec, lc)) && allow_pass[pair(ec, lc)])
                return 0;
            return 1;
        endfunction

        function bit is_strict(int ec, int lc);
            return strict_after.exists(pair(ec, lc)) && strict_after[pair(ec, lc)];
        endfunction
    endclass

    typedef struct {
        longint id;
        longint key;
        int     cls;
        longint data;
        longint seq;        // entry order
        longint cyc_in;
    } fw_order_item_t;

    class fw_order_check extends fw_contract;
        fw_order_rule       rule;
        protected fw_order_item_t m_live[$];          // in entry order
        protected bit             m_seen[longint];    // ids that ever entered
        protected bit             m_left[longint];
        // Items that left in the current cycle, for strict_after.
        protected fw_order_item_t m_last[$];
        protected longint         m_last_cyc = -1;
        protected longint         m_seq;
        int                       n_in, n_out;

        function new(string name, fw_order_rule rule = null);
            super.new(name);
            this.rule = (rule == null) ? fw_order_rule::in_order() : rule;
        endfunction

        function void enter(longint id, longint key = 0, int cls = 0, longint data = 0,
                            longint cyc = 0);
            fw_order_item_t it;
            if (m_seen.exists(id)) begin
                error(FW_E_DUPLICATE, $sformatf("id %0d entered twice", id));
                return;
            end
            it.id = id; it.key = key; it.cls = cls; it.data = data;
            it.seq = m_seq++; it.cyc_in = cyc;
            m_live.push_back(it);
            m_seen[id] = 1;
            n_in++;
        endfunction

        function void leave(longint id, longint data = 0, longint cyc = 0);
            int at = -1;
            fw_order_item_t it;
            if (m_left.exists(id)) begin
                error(FW_E_DUPLICATE, $sformatf("id %0d left twice", id));
                return;
            end
            foreach (m_live[i])
                if (m_live[i].id == id) begin at = i; break; end
            if (at < 0) begin
                error(FW_E_UNKNOWN, $sformatf("id %0d left but never entered", id));
                return;
            end
            it = m_live[at];
            if (it.data != data)
                error(FW_E_DATA, $sformatf("id %0d left with data %0h, entered with %0h",
                                           id, data, it.data));
            for (int i = 0; i < at; i++)
                if (rule.binds(m_live[i].key, m_live[i].cls, it.key, it.cls)) begin
                    error(FW_E_REORDER, $sformatf(
                        "id %0d (key %0d class %0d) left before earlier id %0d (key %0d class %0d)",
                        id, it.key, it.cls, m_live[i].id, m_live[i].key, m_live[i].cls));
                    break;
                end
            if (cyc != m_last_cyc) begin
                m_last.delete();
                m_last_cyc = cyc;
            end
            foreach (m_last[i])
                if (m_last[i].seq < it.seq && rule.is_strict(m_last[i].cls, it.cls)
                        && rule.binds(m_last[i].key, m_last[i].cls, it.key, it.cls))
                    error(FW_E_SAME_CYCLE, $sformatf(
                        "id %0d left in cycle %0d, the same cycle as earlier id %0d",
                        id, cyc, m_last[i].id));
            m_last.push_back(it);
            m_live.delete(at);
            m_left[id] = 1;
            n_out++;
        endfunction

        // The ids that may leave next, in entry order.
        function void legal_next(ref longint ids[$]);
            ids.delete();
            foreach (m_live[j]) begin
                bit ok = 1;
                for (int i = 0; i < j; i++)
                    if (rule.binds(m_live[i].key, m_live[i].cls, m_live[j].key, m_live[j].cls))
                        begin ok = 0; break; end
                if (ok)
                    ids.push_back(m_live[j].id);
            end
        endfunction

        function int in_flight();
            return m_live.size();
        endfunction

        function void finish();
            foreach (m_live[i])
                error(FW_E_LOST, $sformatf("id %0d entered in cycle %0d and never left",
                                           m_live[i].id, m_live[i].cyc_in));
        endfunction
    endclass

    // Allocate / free / use of ids (tags, slots, tokens).
    class fw_lifetime extends fw_contract;
        int                 max_live;           // 0: no bound
        protected bit       m_live[longint];
        int                 peak;

        function new(string name, int max_live = 0);
            super.new(name);
            this.max_live = max_live;
        endfunction

        function void alloc(longint id);
            if (m_live.exists(id)) begin
                error(FW_E_DOUBLE_ALLOC, $sformatf("id %0d allocated while live", id));
                return;
            end
            m_live[id] = 1;
            if (m_live.num() > peak)
                peak = m_live.num();
            if (max_live > 0 && m_live.num() > max_live)
                error(FW_E_MAX_LIVE, $sformatf("%0d ids live, bound %0d", m_live.num(), max_live));
        endfunction

        function void free(longint id);
            if (!m_live.exists(id)) begin
                error(FW_E_BAD_FREE, $sformatf("id %0d freed but not live", id));
                return;
            end
            m_live.delete(id);
        endfunction

        function void use_id(longint id);
            if (!m_live.exists(id))
                error(FW_E_USE_DEAD, $sformatf("id %0d used but not live", id));
        endfunction

        function bit is_live(longint id);
            return m_live.exists(id);
        endfunction

        function int live();
            return m_live.num();
        endfunction

        function void finish();
            foreach (m_live[id])
                error(FW_E_LEAK, $sformatf("id %0d still live at finish", id));
        endfunction
    endclass

    // A dependent waits for the youngest older producer live at its entry.
    class fw_dep_check extends fw_contract;
        protected longint   m_prod_seq[longint];    // live producer id -> entry order
        protected longint   m_dep_on[longint];      // dependent id -> producer id (or -1)
        protected bit       m_retired[longint];
        protected longint   m_seq;

        function new(string name);
            super.new(name);
        endfunction

        function void producer(longint pid);
            m_prod_seq[pid] = m_seq++;
        endfunction

        function void retire(longint pid);
            if (m_prod_seq.exists(pid))
                m_prod_seq.delete(pid);
            m_retired[pid] = 1;
        endfunction

        function void dependent(longint did);
            longint best = -1, best_seq = -1;
            foreach (m_prod_seq[pid])
                if (m_prod_seq[pid] > best_seq) begin
                    best_seq = m_prod_seq[pid];
                    best = pid;
                end
            m_dep_on[did] = best;
            m_seq++;
        endfunction

        function void release_dep(longint did);
            longint pid;
            if (!m_dep_on.exists(did))
                return;
            pid = m_dep_on[did];
            if (pid >= 0 && !m_retired.exists(pid))
                error(FW_E_DEP_EARLY, $sformatf(
                    "dependent %0d released before producer %0d retired", did, pid));
            m_dep_on.delete(did);
        endfunction
    endclass

    // One JSON line per event: {"pt":..,"ev":"in"|"out","cyc":..,"id":..,
    // "key":..,"cls":..,"data":..}.
    class fw_trace;
        protected int fd;

        function new(string path);
            fd = $fopen(path, "w");
            if (fd == 0)
                $display("FW_CONTRACT fw_trace: cannot open %s", path);
        endfunction

        function void event_(string pt, string ev, longint cyc, longint id, longint key = 0,
                             int cls = 0, longint data = 0);
            if (fd != 0)
                $fdisplay(fd, "{\"pt\":\"%s\",\"ev\":\"%s\",\"cyc\":%0d,\"id\":%0d,\"key\":%0d,\"cls\":%0d,\"data\":%0d}",
                          pt, ev, cyc, id, key, cls, data);
        endfunction

        function void close();
            if (fd != 0)
                $fclose(fd);
            fd = 0;
        endfunction
    endclass

endpackage
