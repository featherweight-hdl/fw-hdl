// One comb() object in a domain's settle graph (fw_settle_sched): the comb
// fields its comb() reads and writes, from its class's settle table resolved
// against the instance. A fallback node has no table, or a table entry that
// does not resolve: it may read and write any comb field.
class fw_settle_node;
    fw_combinational c;
    string           name;      // the owning component, for errors
    fw_settle_table  tbl;       // null: fallback
    bit              fallback;
    string           why;       // why it is a fallback, for the report
    fw_sync_field    reads[$], writes[$];
    fw_sync_field    dep_w[$], dep_r[$];  // comb write dep_w[i] reads dep_r[i]
    int              succ[$];   // nodes that read a field this one writes

    // Tarjan's state.
    int              index = -1, low;
    bit              on_stack;

    function new(fw_combinational c, string name);
        this.c    = c;
        this.name = name;
    endfunction
endclass
