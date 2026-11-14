// Tells whether a comb() object is an instance of one class, so the
// scheduler can find its settle table (fw_settle_table.find_for()). SV has no
// run-time class name ($typename gives the static type), so the settle
// weaver registers one fw_settle_is#(C) per specialization C it sees, with
// the number of C's base classes: of several matches (a subclass matches its
// bases too), the deepest is the instance's own class.
virtual class fw_settle_match;
    int unsigned depth;

    function new(int unsigned depth);
        this.depth = depth;
    endfunction

    pure virtual function bit test(fw_combinational c);
endclass
