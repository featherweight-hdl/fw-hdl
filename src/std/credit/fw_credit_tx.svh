
// fw_credit_tx -- a credit-gated sender (first cut of RQ-L2: one VC, no pool).
//
//   in   values to send (a stream);
//   cr   credit returns, one bit per credit (a stream);
//   out  the sent values, valid-only: the sender never offers a value without
//        a credit, so the receiver never has to stall it.
//
// It starts with CREDITS credits: the receiver's buffer depth. Per value it
// spends one; a return gives one back. It waits for a return only when it has
// none.
//
// Per cycle (RTL, fw.hdl.lib xls lowering): it takes a value when it has a
// credit, and takes a credit return every cycle, so a return never waits
// behind data. Recognized by the registry: the body below is the model and is
// not mapped.
class fw_credit_tx #(type T = bit [7:0], int CREDITS = 2) extends fw_component
        implements fw_runnable;
    fw_port #(fw_get_if #(T))       in;
    fw_port #(fw_get_if #(bit))     cr;
    fw_port #(fw_valid_put_if #(T)) out;
    protected int                   m_credits = CREDITS;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_runnable(this);
    endfunction

    function void build();
        in = new("in", this);
        cr = new("cr", this);
        out = new("out", this);
    endfunction

    virtual task run();
        forever begin
            T   x;
            bit c;
            in.t.get(x);
            if (m_credits == 0) begin
                cr.t.get(c);
                m_credits++;
            end
            out.t.put(x);
            m_credits--;
        end
    endtask
endclass
