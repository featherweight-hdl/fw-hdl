// One clock domain's share of the sync kernel: the holders it commits, the
// comb()s it settles and the step()s it calls at each edge of `clk`. The
// kernel (fw_sync_kernel) builds one per domain from the component tree.
class fw_sync_dom;
    fw_domain_if        key;     // domain_equiv() of the domain; null: unclocked
    fw_clock_domain_if  clk;     // what the kernel ticks on (null: unclocked)
    fw_sig_holder       holders[$];
    fw_combinational    combs[$];
    string              comb_names[$];   // the owning component, for errors
    fw_steppable        steps[$];
    fw_settle_sched     sched;           // built by the kernel's elaborate()
    int unsigned        edge_evals;      // comb() calls in the last settle
    longint unsigned    n_evals;         // comb() calls, all settles
    // The domain's edges run so far, and the time of the last one: task
    // code is at edge edge_n while $realtime == edge_t (fw_sig_holder).
    longint unsigned    edge_n;
    realtime            edge_t = -1;

    function new(fw_domain_if key, fw_clock_domain_if clk);
        this.key = key;
        this.clk = clk;
    endfunction
endclass

// The domains whose root is one edge driver's, with each one's divisor: the
// kernel runs, at root edge k, those whose divisor divides k (one group).
class fw_sync_group;
    fw_edge_driver   drv;
    fw_sync_dom      doms[$];
    longint unsigned divs[$];

    function new(fw_edge_driver drv);
        this.drv = drv;
    endfunction
endclass
