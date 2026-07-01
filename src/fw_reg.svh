
// fw_reg #(T) -- a register typed over a packed struct T that lays out the
// fields. T is 2-state (`bit`) so the synthesis front end recovers field offsets
// directly from member layout -- there are no field objects to lower, and a
// field is just a slice of T. W defaults to $bits(T).
//
// On top of the untyped fw_reg_base value API it adds the NATIVE projection:
//   read()        -> T          (canonical value as a struct; pure, no clear)
//   write(v)      : task        (software-style write of a struct value)
//   update(v,m)   : task        (hardware masked update, inline struct literals)
//
// Named-field access falls out for free: r.read().ch_en; and a single bit is
// poked with   r.update('{default:'0, done:1}, '{default:'0, done:1});
class fw_reg #(type T = bit, int W = $bits(T)) extends fw_reg_base #(W)
        implements fw_reg_val_if #(W);

    function new(string name,
                 fw_reg_block #(W) parent,
                 int offset  = -1,
                 T reset     = '0,
                 T sw_wmask  = '1,
                 T hw_wmask  = '0,
                 T rclr_mask = '0);
        super.new(name, parent, offset, reset, sw_wmask, hw_wmask, rclr_mask);
    endfunction

    // native projection of the canonical value (single source of truth, no side
    // effects) -- safe for hardware to peek a register whose value it supplies.
    function T   read();            return T'(read_val());        endfunction
    task         write(input T v);  write_val(W'(v));             endtask
    // hardware-facing masked update, written inline with struct literals.
    task         update(input T v, input T mask = '1);
                                    update_val(W'(v), W'(mask));  endtask
endclass
