// The sync kernel (fw-hdl-spec semantics/processes.md, "The edge";
// sync-task-domains.md §2.2, §6.5). At each edge of a root clock, over the
// group of domains that edge there (the root and the derived domains that
// divide it):
//   1. evaluate: call every step(); they read current values and write the
//      next ones,
//   2. update: commit every sync field,
//   3. settle: call every comb() until no comb value changes,
//   4. release: the root's edge driver resumes the tasks waiting on it.
// So related domains at one time behave as flops on one clock tree, and a
// task resumes after its edge's update. Task code then touches fields as
// crossing ports (fw_sig_holder): reads at the edge see the values from
// before it, writes land at once and settle (settle_now).
// Settle runs the domain's schedule (fw_settle_sched, from the woven settle
// tables): each comb() once in dependency order, comb loops and classes
// without a table iterated, at most max_passes, with a named error if they
// don't converge. `naive` (plusarg +fw_settle_naive) runs whole passes over
// all the domain's comb()s instead, for comparison. At elaborate, a true
// comb loop that no component waived is fatal; +fw_settle_show prints each
// domain's schedule (fw_settle_sched::report()).
//
// The root makes one after build (freeze_tree) and connect (elaborate), and
// launches it with the run phase. A tree with no struct ports and no comb()
// leaves it inactive: step()s are then forked by do_run() as before. A
// domain whose root has no edge driver (a root bridge outside fw-hdl) gets
// its own loop, one do_edge() per tick().
class fw_sync_kernel;
    string       name;          // the root, for errors
    int unsigned max_passes = 64;
    bit          naive;         // settle by whole passes, not the schedule
    bit          active;
    fw_sync_dom  doms[$];
    fw_sync_group groups[$];    // by root edge driver, built by launch()

    function new(string name = "");
        this.name = name;
    endfunction

    // End of build: the woven fw_sp_comb declarations are applied, then the
    // field semantics of every holder are fixed.
    static function void freeze_tree(fw_component top);
        fw_sync_net ns[$];
        fw_sp_comb::apply_tree(top);
        fw_sync_conn::nets(top, ns);
        foreach (ns[i]) ns[i].holder.freeze();
    endfunction

    // After connect: freeze, check the connections (fatal), and sort the
    // tree's holders, comb()s and step()s into clock domains.
    function void elaborate(fw_component top);
        fw_sync_net ns[$];
        fw_sync_bridge::resolve_tree(top);
        freeze_tree(top);
        fw_sync_conn::check(top);
        fw_sync_conn::nets(top, ns);
        foreach (ns[i]) begin
            fw_sync_dom d = m_dom(ns[i].ends[0].owner);
            d.holders.push_back(ns[i].holder);
            ns[i].holder.kernel = this;
            ns[i].holder.dom    = d;
            // Reset-force reads the reset domain of the first owned end
            // (a pin bridge's end has no owner).
            foreach (ns[i].ends[j]) begin
                fw_component c = ns[i].ends[j].owner;
                if (ns[i].holder.rst == null && c != null && c.reset.is_connected())
                    ns[i].holder.set_reset(c.reset.get_if());
            end
        end
        m_collect(top);
        if ($test$plusargs("fw_settle_naive")) naive = 1;
        foreach (doms[i]) begin
            doms[i].sched = fw_settle_sched::build(doms[i]);
            if ($test$plusargs("fw_settle_show"))
                $display("fw_settle: %s domain %0d: %s", name, i, doms[i].sched.report());
            if (doms[i].sched.loop_err != "")
                $fatal(1, "fw-hdl: %s: %s", name, doms[i].sched.loop_err);
        end
        active = (ns.size() != 0);
        foreach (doms[i]) if (doms[i].combs.size() != 0) active = 1;
    endfunction

    // The run phase: the domains are grouped by their root's edge driver,
    // and one process per root runs each root edge's group, then releases
    // the edge. Called from the root's start(), so its `disable fork` ends
    // them.
    task launch();
        fw_sig_holder::phase = FW_SYNC_PH_RUN;
        fw_sig_holder::gen++;
        groups.delete();
        foreach (doms[i]) begin
            fw_edge_driver   drv;
            longint unsigned div;
            fw_sync_group    g;
            if (doms[i].clk == null) continue;
            drv = fw_edge_driver::of(doms[i].clk, div);
            if (drv == null) begin
                m_launch_dom(doms[i]);
                continue;
            end
            foreach (groups[j]) if (groups[j].drv == drv) g = groups[j];
            if (g == null) begin
                g = new(drv);
                groups.push_back(g);
            end
            g.doms.push_back(doms[i]);
            g.divs.push_back(div);
        end
        foreach (groups[i]) m_launch_group(groups[i]);
    endtask

    // Root edge k of g's root: the group is the domains whose divisor
    // divides k (their edges are fixed from time 0).
    protected task m_launch_group(fw_sync_group g);
        g.drv.own();
        fork
            forever begin
                string           err;
                fw_sync_dom      ds[$];
                longint unsigned k = g.drv.released + 1;
                g.drv.wait_edge(k);
                foreach (g.doms[j]) if (k % g.divs[j] == 0) ds.push_back(g.doms[j]);
                if (do_group(ds, err)) $fatal(1, "fw-hdl: %s: %s", name, err);
                g.drv.release_edge(k);
            end
        join_none
    endtask

    // A domain whose root has no edge driver: one do_edge() per tick().
    protected task m_launch_dom(fw_sync_dom d);
        fork
            forever begin
                string err;
                d.clk.tick(1);
                if (do_edge(d, err)) $fatal(1, "fw-hdl: %s: %s", name, err);
            end
        join_none
    endtask

    // One edge of domain d alone (a group of one).
    function bit do_edge(fw_sync_dom d, output string err);
        fw_sync_dom ds[$];
        ds.push_back(d);
        return do_group(ds, err);
    endfunction

    // One edge of the domains in ds, together: every step(), then every
    // commit, then each domain's settle. Returns 1 and the error in err if
    // a settle does not converge. Leaves the phase as it found it.
    function bit do_group(fw_sync_dom ds[$], output string err);
        fw_sync_phase_e prev = fw_sig_holder::phase;
        err = "";
        foreach (ds[k]) begin
            ds[k].edge_n++;
            ds[k].edge_t = $realtime;
        end
        fw_sig_holder::phase = FW_SYNC_PH_STEP;
        foreach (ds[k]) begin
            foreach (ds[k].steps[i]) begin
                fw_atomic_steppable a;
                void'($cast(a, ds[k].steps[i]));
                if (a != null) a.step_save();
                fw_step_ctx::begin_step(a);
                ds[k].steps[i].step();
                if (!fw_step_ctx::end_step()) a.step_restore();
            end
        end
        fw_sig_holder::phase = prev;
        foreach (ds[k]) foreach (ds[k].holders[i]) ds[k].holders[i].commit();
        foreach (ds[k]) begin
            if (settle(ds[k], err)) begin
                fw_sig_holder::phase = prev;
                return 1;
            end
        end
        fw_sig_holder::phase = prev;
        fw_sig_holder::gen++;
        return 0;
    endfunction

    // A pin bridge wrote a field of h from outside the tree, between edges
    // or after this edge's group: settle h's domain now, so the comb paths
    // through the class tree reach the other pins in the same time step
    // (design §3.3, "Mixed SV/RTL simulation"). Fatal if it does not
    // converge.
    function void settle_now(fw_sig_holder h);
        string err;
        if (h.dom == null) return;
        if (settle(h.dom, err)) $fatal(1, "fw-hdl: %s: %s", name, err);
        fw_sig_holder::gen++;
    endfunction

    // Settle d's comb values: by its schedule, or (naive, or no schedule)
    // by whole passes. On no convergence, err names the components whose
    // comb() still changed a value in the last pass.
    function bit settle(fw_sync_dom d, output string err);
        fw_sync_phase_e prev = fw_sig_holder::phase;
        int unsigned    evals;
        bit             e;
        fw_sig_holder::phase = FW_SYNC_PH_COMB;
        if (naive || d.sched == null) e = m_settle_naive(d, err, evals);
        else                          e = d.sched.run(max_passes, err, evals);
        d.edge_evals = evals;
        d.n_evals   += evals;
        fw_sig_holder::phase = prev;
        return e;
    endfunction

    // Call every comb() of d until a whole pass changes no comb value.
    protected function bit m_settle_naive(fw_sync_dom d, output string err,
                                          output int unsigned evals);
        string who;
        err   = "";
        evals = 0;
        for (int p = 0; p < max_passes; p++) begin
            int unsigned n_pass = fw_sig_holder::comb_changes;
            who = "";
            foreach (d.combs[i]) begin
                int unsigned n_was = fw_sig_holder::comb_changes;
                d.combs[i].comb();
                if (fw_sig_holder::comb_changes != n_was)
                    who = (who == "") ? d.comb_names[i]
                                      : {who, ", ", d.comb_names[i]};
            end
            evals += d.combs.size();
            if (fw_sig_holder::comb_changes == n_pass) return 0;
        end
        err = $sformatf("comb() did not settle in %0d passes (a comb loop?); still changing: %s",
                        max_passes, who);
        return 1;
    endfunction

    // The domain of component c (by domain_equiv(); unclocked: null).
    protected function fw_sync_dom m_dom(fw_component c);
        fw_clock_domain_if clk = null;
        fw_domain_if       key = null;
        fw_sync_dom        d;
        if (c != null && c.clock.is_connected()) begin
            clk = c.clock.get_if();
            key = clk.domain_equiv();
        end
        foreach (doms[i]) if (doms[i].key == key) return doms[i];
        d = new(key, clk);
        doms.push_back(d);
        return d;
    endfunction

    protected function void m_collect(fw_component c);
        fw_combinational cs[$];
        fw_steppable     ss[$];
        fw_component     kids[$];
        fw_sync_dom      d;
        c.get_combs(cs);
        c.get_steppables(ss);
        if (cs.size() != 0 || ss.size() != 0) begin
            d = m_dom(c);
            foreach (cs[i]) begin
                d.combs.push_back(cs[i]);
                d.comb_names.push_back(c.get_full_name());
            end
            foreach (ss[i]) d.steps.push_back(ss[i]);
        end
        c.get_children(kids);
        foreach (kids[i]) m_collect(kids[i]);
    endfunction
endclass
