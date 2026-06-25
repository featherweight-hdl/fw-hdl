
// HARDWARE WRITE OBSERVER (one of the two hardware-facing register hooks).
//
// Implemented by the hardware that reacts to a SOFTWARE write. Fired AFTER the
// write commits (post sw_wmask), so the observer sees the new value. TASK
// context, so it may activate clock-synchronized behavior -- e.g. "CH_EN was set
// -> start the engine". A register may have zero or more observers.
//
//   val  = new committed value (post sw_wmask)
//   prev = value before this write
//
// See fw_reg_rd_if for the read-side hook.
interface class fw_reg_wr_if #(int W = 32);
    pure virtual task on_write(input bit [W-1:0] val, input bit [W-1:0] prev);
endclass
