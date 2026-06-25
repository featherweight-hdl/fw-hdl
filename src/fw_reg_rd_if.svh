
// HARDWARE READ PROVIDER (one of the two hardware-facing register hooks).
//
// Implemented by the hardware that owns a register's value; it supplies what
// SOFTWARE should observe on a read. `stored` is the register's last-committed
// value; the default (no provider attached) returns it as-is, but a provider may
// instead return live hardware state (e.g. a BUSY bit that mirrors an engine FSM
// state, costing no storage). FUNCTION context: a read must not consume time.
//
// See fw_reg_wr_if for the write-side hook. The two are deliberately separate
// interface classes so the read path (pure, value-returning) and the write path
// (time-consuming, reactive) are independently implementable.
interface class fw_reg_rd_if #(int W = 32);
    pure virtual function bit [W-1:0] on_read(input bit [W-1:0] stored);
endclass
