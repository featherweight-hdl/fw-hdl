
typedef class fw_edge_driver;

// A root clock domain that has an edge driver (fw_clock_xtor_bridge,
// fw_clock_period_xtor_bridge). A separate interface class, so that
// fw_clock_domain_if keeps its methods: a root outside fw-hdl that doesn't
// implement this keeps the old tick() behavior.
interface class fw_edge_source;
    pure virtual function fw_edge_driver edge_driver();
endclass

// The edge driver of one root clock domain (sync-task-domains.md §6.5;
// fw-hdl-spec semantics/processes.md, "Edges" and "The edge").
//
// A root's edges are counted from time 0, whoever looks and whenever the
// tree was elaborated: a net clock's by its interface (fw_clock_xtor_if, a
// rise to 1), a period clock's from the time (edge k at k * period). A
// derived domain that divides the root by div has its edges at root edges
// j * div, so its phase is fixed from time 0 too.
//
// Once a sync kernel owns the root (own(), at launch), it runs the group of
// each root edge (evaluate, update, settle, over the root and the derived
// domains that edge there) and then releases the edge. tick() then waits
// for releases, by count, so a task resumes after its edge's update. Before
// that, tick() waits for the edges themselves.
virtual class fw_edge_driver;
    longint unsigned released;   // root edges released so far
    bit              owned;      // a sync kernel releases this root's edges
    protected event  m_rel;

    // The root's edges at or before now.
    pure virtual function longint unsigned edges();
    // Returns at root edge k (at once if it has passed).
    pure virtual task wait_edge(longint unsigned k);

    // The root edges a task has passed, once a kernel owns the root: those
    // released. A computed edge (a period root) due now counts too, since
    // it comes before a delay that ends at its time.
    protected virtual function longint unsigned m_pos();
        return released;
    endfunction

    // A sync kernel owns the root from now: the edges so far count as
    // released. A kernel launched again (a new tree) takes it over.
    function void own();
        owned    = 1;
        released = edges();
    endfunction

    // The kernel has run root edge k's group: resume the tasks waiting on it.
    function void release_edge(longint unsigned k);
        released = k;
        ->m_rel;
    endfunction

    // n edges of a domain that divides this root by div: to its n-th edge
    // after the last one this task has passed (by count, never by time).
    task tick(longint unsigned div, int n);
        longint unsigned t;
        if (n <= 0) begin
            #0;
            return;
        end
        t = ((owned ? m_pos() : edges()) / div + n) * div;
        // A kernel that took the root over during the wait releases edge t
        // after the edge itself: resume after that, as if owned throughout.
        if (!owned) wait_edge(t);
        if (owned) while (released < t) @(m_rel);
    endtask

    // The edge driver of the root of clock domain d, with d's divisor in
    // div; null if that root has none.
    static function fw_edge_driver of(fw_domain_if d, output longint unsigned div);
        fw_edge_source     s;
        fw_clock_domain_if c;
        fw_domain_if       r = d;
        div = 1;
        if (d == null) return null;
        while (r.domain_nsrc() == 1 && r.domain_src(0) != null) r = r.domain_src(0);
        if (r.domain_nsrc() != 0 || !$cast(s, r)) return null;
        if ($cast(c, d)) div = c.root_ticks(1);
        return s.edge_driver();
    endfunction
endclass
