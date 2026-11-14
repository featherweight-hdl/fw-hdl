// The sync kernel (design-sync-rtl §3.3): at each edge of each clock domain,
//   1. commit the sync fields written since the last edge,
//   2. settle: call every comb() until no comb value changes,
//   3. call the step()s.
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
// leaves it inactive: step()s are then forked by do_run() as before.
class fw_sync_kernel;
    string       name;          // the root, for errors
    int unsigned max_passes = 64;
    bit          naive;         // settle by whole passes, not the schedule
    bit          active;
    fw_sync_dom  doms[$];

    // run() ordering: a run() and the kernel wake on the same edge in no set
    // order, but a run() must see what that edge's step()s see (design §3.3:
    // the kernel releases the run()s). With a kernel launched (m_live), the
    // root clock bridges call after_tick() at the end of tick(): every
    // process but the kernel's own (m_procs) then yields with #0, so it
    // resumes after the kernel's do_edge() at this time.
    static bit          m_live;
    static std::process m_procs[$];

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

    // The run phase: one process per domain, one do_edge() per tick. Called
    // from the root's start(), so its `disable fork` ends them.
    task launch();
        fw_sig_holder::phase = FW_SYNC_PH_RUN;
        m_live = 1;
        fw_sig_holder::gen++;
        foreach (doms[i]) begin
            automatic fw_sync_dom d = doms[i];
            if (d.clk == null) continue;
            fork
                begin
                    m_procs.push_back(std::process::self());
                    forever begin
                        string err;
                        d.clk.tick(1);
                        if (do_edge(d, err)) $fatal(1, "fw-hdl: %s: %s", name, err);
                    end
                end
            join_none
        end
    endtask

    static task after_tick();
        std::process p;
        if (!m_live) return;
        p = std::process::self();
        foreach (m_procs[i]) if (m_procs[i] == p) return;
        #0;
    endtask

    // One edge of domain d: commit, settle, step. Returns 1 and the error
    // in err if settle does not converge (the steps are then not called).
    // Leaves the phase as it found it.
    function bit do_edge(fw_sync_dom d, output string err);
        fw_sync_phase_e prev = fw_sig_holder::phase;
        err = "";
        foreach (d.holders[i]) d.holders[i].commit();
        if (settle(d, err)) begin
            fw_sig_holder::phase = prev;
            return 1;
        end
        fw_sig_holder::phase = FW_SYNC_PH_STEP;
        foreach (d.steps[i]) begin
            fw_atomic_steppable a;
            void'($cast(a, d.steps[i]));
            if (a != null) a.step_save();
            fw_step_ctx::begin_step(a);
            d.steps[i].step();
            if (!fw_step_ctx::end_step()) a.step_restore();
        end
        fw_sig_holder::phase = prev;
        fw_sig_holder::gen++;
        return 0;
    endfunction

    // A pin bridge wrote a comb field of h from outside the tree, between
    // edges or after this edge's do_edge(): settle h's domain now, so the
    // comb paths through the class tree reach the other pins in the same
    // time step (design §3.3, "Mixed SV/RTL simulation"). Fatal if it does
    // not converge.
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
