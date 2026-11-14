// The settle schedule of one clock domain (design-sync-rtl §4.6, plan S4.3).
// Built once after connect from the domain's comb()s and the woven settle
// tables (fw_settle_table): a node per comb() object, an edge A -> B when
// A's comb() writes a comb field that B's comb() reads, Tarjan's SCCs, and a
// topological order of them. Per settle, an acyclic node runs once; a group
// (an SCC of several nodes, or one that reads what it writes) runs whole
// passes until a pass changes no comb value, at most max_passes.
//
// A node without a usable table (fallback) may read and write any comb
// field: it is joined to every node that reads or writes one, so the
// fallbacks and every node that both reads and writes share one group,
// which then settles like the naive kernel did.
//
// Each looping group is classified at connect from the field-level graph
// (comb field r -> comb field w when a node's comb() writes w from r, by the
// table's per-write dependences): a false cycle has no field-level cycle (a
// comb() serving independent paths); a true loop has one, and is an error
// naming its fields unless a component in it has waive_comb_loop(). Both
// still settle by passes. report() (printed under +fw_settle_show) lists the
// schedule, the groups and their kinds, and the fallbacks.
typedef class fw_sync_dom;

class fw_settle_sched;
    fw_settle_node nodes[$];
    int            seq[$];        // node indices, groups in topological order
    int            grp_first[$];  // per group: its first entry in seq
    int            grp_size[$];
    bit            grp_loop[$];   // iterates (else: each node runs once)
    string         grp_kind[$];   // "once", "false cycle", "true loop", "fallback"
    string         grp_fields[$]; // a true loop's cycle, a false cycle's shared fields
    string         grp_waiver[$]; // a waived true loop: the reason
    string         loop_err;      // the unwaived true loops ("": none)
    int unsigned   n_fallback;

    // Field names for reports: the first path that resolved to each field.
    protected fw_sync_field m_fl[$];
    protected string        m_fn[$];

    // Field-level DFS state (m_classify).
    protected int  m_fadj[$][$];
    protected int  m_color[$];
    protected int  m_fpath[$];
    protected int  m_cyc[$];

    // Tarjan's state.
    protected int  m_index;
    protected int  m_stack[$];
    protected int  m_sccs[$][$];  // in reverse topological order

    // The schedule of d's comb()s.
    static function fw_settle_sched build(fw_sync_dom d);
        fw_settle_sched s = new();
        foreach (d.combs[i]) begin
            fw_settle_node n = new(d.combs[i], d.comb_names[i]);
            s.m_resolve(n);
            if (n.fallback) s.n_fallback++;
            s.nodes.push_back(n);
        end
        s.m_edges();
        s.m_order();
        s.m_classify();
        return s;
    endfunction

    // Settle once: returns 1 and the error in err if a group does not
    // converge. evals: the comb() calls made. The caller sets the phase.
    function bit run(int unsigned max_passes, output string err,
                     output int unsigned evals);
        err   = "";
        evals = 0;
        foreach (grp_first[g]) begin
            int f = grp_first[g];
            if (!grp_loop[g]) begin
                for (int k = 0; k < grp_size[g]; k++) nodes[seq[f+k]].c.comb();
                evals += grp_size[g];
                continue;
            end
            begin
                string who;
                bit    done = 0;
                for (int p = 0; p < max_passes && !done; p++) begin
                    int unsigned n_pass = fw_sig_holder::comb_changes;
                    who = "";
                    for (int k = 0; k < grp_size[g]; k++) begin
                        fw_settle_node n     = nodes[seq[f+k]];
                        int unsigned   n_was = fw_sig_holder::comb_changes;
                        n.c.comb();
                        if (fw_sig_holder::comb_changes != n_was)
                            who = (who == "") ? n.name : {who, ", ", n.name};
                    end
                    evals += grp_size[g];
                    done = (fw_sig_holder::comb_changes == n_pass);
                end
                if (!done) begin
                    err = $sformatf("comb() did not settle in %0d passes (a comb loop?); still changing: %s",
                                    max_passes, who);
                    return 1;
                end
            end
        end
        return 0;
    endfunction

    // n's comb fields from its table. A table path is "<port>.<field>",
    // where <port> may be prefixed by child component names ("sub.in.f").
    protected function void m_resolve(fw_settle_node n);
        fw_component comp;
        n.tbl = fw_settle_table::find_for(n.c);
        if (n.tbl == null) begin
            n.fallback = 1;
            n.why      = "no settle table";
            return;
        end
        if (!$cast(comp, n.c)) begin
            n.fallback = 1;
            n.why      = "comb() object is not a component";
            return;
        end
        foreach (n.tbl.comb_reads[i])
            if (m_path(n, comp, n.tbl.comb_reads[i], n.reads)) return;
        foreach (n.tbl.comb_writes[i])
            if (m_path(n, comp, n.tbl.comb_writes[i], n.writes)) return;
        if (!n.tbl.deps_known) begin
            foreach (n.writes[i]) foreach (n.reads[j]) begin
                n.dep_w.push_back(n.writes[i]);
                n.dep_r.push_back(n.reads[j]);
            end
            return;
        end
        foreach (n.tbl.comb_dep_w[i]) begin
            fw_sync_field w = m_find(n, comp, n.tbl.comb_dep_w[i]);
            fw_sync_field r;
            if (w == null) return;
            r = m_find(n, comp, n.tbl.comb_dep_r[i]);
            if (r == null) return;
            if (w.comb && r.comb) begin
                n.dep_w.push_back(w);
                n.dep_r.push_back(r);
            end
        end
    endfunction

    // Resolve one path and add its field to fs if comb. Returns 1 (and
    // makes n a fallback) if it does not resolve.
    protected function bit m_path(fw_settle_node n, fw_component comp,
                                  string path, ref fw_sync_field fs[$]);
        fw_sync_field f = m_find(n, comp, path);
        if (f == null) return 1;
        if (f.comb) fs.push_back(f);
        return 0;
    endfunction

    // The field of one path; null (and n a fallback) if it does not resolve.
    protected function fw_sync_field m_find(fw_settle_node n, fw_component comp,
                                            string path);
        string        segs[$];
        string        fname;
        fw_sync_field f = null;
        m_split(path, segs);
        fname = segs.pop_back();
        while (segs.size() != 0 && comp != null && f == null) begin
            fw_sync_port ps[$];
            fw_component kids[$];
            string       pname = m_join(segs);
            comp.get_sync_ports(ps);
            foreach (ps[i]) begin
                if (ps[i].name == pname && ps[i].holder() != null) begin
                    f = ps[i].holder().field(fname);
                    break;
                end
            end
            if (f != null) break;
            comp.get_children(kids);
            begin
                fw_component next = null;
                foreach (kids[i]) if (kids[i].get_name() == segs[0]) next = kids[i];
                comp = next;
            end
            void'(segs.pop_front());
        end
        if (f == null) begin
            n.fallback = 1;
            n.why      = {"path ", path, " does not resolve"};
            n.reads.delete();
            n.writes.delete();
            n.dep_w.delete();
            n.dep_r.delete();
            return null;
        end
        if (m_fid(f, 0, m_fl) < 0) begin
            m_fl.push_back(f);
            m_fn.push_back({n.name, ".", path});
        end
        return f;
    endfunction

    // f's index in fl (add: appending it if absent); -1 if absent.
    protected static function int m_fid(fw_sync_field f, input bit add,
                                        ref fw_sync_field fl[$]);
        foreach (fl[i]) if (fl[i] == f) return i;
        if (!add) return -1;
        fl.push_back(f);
        return fl.size() - 1;
    endfunction

    protected function string m_fname(fw_sync_field f);
        int i = m_fid(f, 0, m_fl);
        return (i < 0) ? f.name : m_fn[i];
    endfunction

    // Classify each group (see the header) and collect loop_err.
    protected function void m_classify();
        loop_err = "";
        foreach (grp_first[g]) begin
            int           f    = grp_first[g];
            fw_sync_field fl[$];
            string        kind = "once", flds = "", waiver = "", names = "";
            bit           fb   = 0;
            grp_kind.push_back("");
            grp_fields.push_back("");
            grp_waiver.push_back("");
            if (!grp_loop[g]) begin
                grp_kind[g] = kind;
                continue;
            end
            m_fadj.delete();
            for (int k = 0; k < grp_size[g]; k++) begin
                fw_settle_node n = nodes[seq[f+k]];
                fw_component   c;
                if (n.fallback) fb = 1;
                if ($cast(c, n.c) && c.comb_loop_waiver() != "" && waiver == "")
                    waiver = c.comb_loop_waiver();
                names = (names == "") ? n.name : {names, ", ", n.name};
                foreach (n.dep_w[i]) begin
                    int r = m_fid(n.dep_r[i], 1, fl);
                    int w = m_fid(n.dep_w[i], 1, fl);
                    while (m_fadj.size() < fl.size()) m_fadj.push_back('{});
                    m_fadj[r].push_back(w);
                end
            end
            if (fb) begin
                grp_kind[g] = "fallback";
                continue;
            end
            m_color.delete();
            m_cyc.delete();
            m_fpath.delete();
            foreach (fl[i]) m_color.push_back(0);
            foreach (fl[i]) if (m_cyc.size() == 0 && m_color[i] == 0) void'(m_dfs(i));
            if (m_cyc.size() == 0) begin
                // The fields one node writes and another reads.
                kind = "false cycle";
                foreach (fl[i]) begin
                    bit wr = 0, rd = 0;
                    for (int k = 0; k < grp_size[g]; k++) begin
                        fw_settle_node n = nodes[seq[f+k]];
                        foreach (n.writes[j]) if (n.writes[j] == fl[i]) wr = 1;
                        foreach (n.reads[j])  if (n.reads[j]  == fl[i]) rd = 1;
                    end
                    if (wr && rd) flds = (flds == "") ? m_fname(fl[i]) : {flds, ", ", m_fname(fl[i])};
                end
            end else begin
                kind = "true loop";
                foreach (m_cyc[i])
                    flds = (i == 0) ? m_fname(fl[m_cyc[i]]) : {flds, " -> ", m_fname(fl[m_cyc[i]])};
                flds = {flds, " -> ", m_fname(fl[m_cyc[0]])};
                if (waiver == "")
                    loop_err = {loop_err, (loop_err == "") ? "" : "; ",
                                "comb loop through ", flds, " (comb() of ", names, ")"};
            end
            grp_kind[g]   = kind;
            grp_fields[g] = flds;
            if (kind == "true loop") grp_waiver[g] = waiver;
        end
        m_fadj.delete();
    endfunction

    // DFS over m_fadj from v; on a back edge, m_cyc gets the cycle.
    protected function bit m_dfs(int v);
        m_color[v] = 1;
        m_fpath.push_back(v);
        foreach (m_fadj[v][j]) begin
            int w = m_fadj[v][j];
            if (m_color[w] == 1) begin
                int st = 0;
                foreach (m_fpath[i]) if (m_fpath[i] == w) st = i;
                for (int i = st; i < m_fpath.size(); i++) m_cyc.push_back(m_fpath[i]);
                return 1;
            end
            if (m_color[w] == 0 && m_dfs(w)) return 1;
        end
        m_color[v] = 2;
        void'(m_fpath.pop_back());
        return 0;
    endfunction

    // The connect-time report (+fw_settle_show).
    function string report();
        string s = $sformatf("%0d comb() nodes, %0d groups, %0d fallback",
                             nodes.size(), grp_first.size(), n_fallback);
        foreach (grp_first[g]) begin
            string names = "";
            for (int k = 0; k < grp_size[g]; k++)
                names = (k == 0) ? nodes[seq[grp_first[g]+k]].name
                                 : {names, ", ", nodes[seq[grp_first[g]+k]].name};
            s = {s, $sformatf("\n  group %0d: %s: %s", g, grp_kind[g], names)};
            if (grp_fields[g] != "") s = {s, "\n    fields: ", grp_fields[g]};
            if (grp_waiver[g] != "") s = {s, "\n    waived: ", grp_waiver[g]};
        end
        foreach (nodes[i])
            if (nodes[i].fallback)
                s = {s, "\n  fallback ", nodes[i].name, ": ", nodes[i].why};
        return s;
    endfunction

    protected function void m_edges();
        foreach (nodes[a]) begin
            foreach (nodes[b]) begin
                if (m_feeds(nodes[a], nodes[b])) nodes[a].succ.push_back(b);
            end
        end
    endfunction

    // Does a's comb() write a comb field that b's comb() reads?
    protected function bit m_feeds(fw_settle_node a, fw_settle_node b);
        if (a.fallback) return b.fallback || b.reads.size() != 0;
        if (b.fallback) return a.writes.size() != 0;
        foreach (a.writes[i])
            foreach (b.reads[j])
                if (a.writes[i] == b.reads[j]) return 1;
        return 0;
    endfunction

    protected function void m_order();
        m_index = 0;
        foreach (nodes[i]) if (nodes[i].index < 0) m_tarjan(i);
        for (int k = m_sccs.size() - 1; k >= 0; k--) begin
            bit loop = (m_sccs[k].size() > 1);
            int v    = m_sccs[k][0];
            foreach (nodes[v].succ[j]) if (nodes[v].succ[j] == v) loop = 1;
            grp_first.push_back(seq.size());
            grp_size.push_back(m_sccs[k].size());
            grp_loop.push_back(loop);
            // In declaration order within the group.
            m_sccs[k].sort();
            foreach (m_sccs[k][j]) seq.push_back(m_sccs[k][j]);
        end
        m_sccs.delete();
    endfunction

    protected function void m_tarjan(int v);
        fw_settle_node n = nodes[v];
        n.index    = m_index;
        n.low      = m_index;
        m_index++;
        m_stack.push_back(v);
        n.on_stack = 1;
        foreach (n.succ[j]) begin
            int w = n.succ[j];
            if (nodes[w].index < 0) begin
                m_tarjan(w);
                if (nodes[w].low < n.low) n.low = nodes[w].low;
            end else if (nodes[w].on_stack && nodes[w].index < n.low) begin
                n.low = nodes[w].index;
            end
        end
        if (n.low == n.index) begin
            int scc[$];
            int w;
            do begin
                w = m_stack.pop_back();
                nodes[w].on_stack = 0;
                scc.push_back(w);
            end while (w != v);
            m_sccs.push_back(scc);
        end
    endfunction

    protected static function void m_split(string s, ref string segs[$]);
        int st = 0;
        for (int i = 0; i <= s.len(); i++) begin
            if (i == s.len() || s[i] == ".") begin
                segs.push_back(s.substr(st, i - 1));
                st = i + 1;
            end
        end
    endfunction

    protected static function string m_join(string segs[$]);
        string r = segs[0];
        for (int i = 1; i < segs.size(); i++) r = {r, ".", segs[i]};
        return r;
    endfunction
endclass
