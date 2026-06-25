
// Untyped (value-level) register API. A register group (fw_reg_block) holds its
// entries as fw_reg_val_if #(W) so it can decode/iterate without knowing the
// per-register packed-struct type T.
//
//   read_val()  -- the CANONICAL value (read provider applied if present). PURE:
//                  no side effects, so a hardware read() peek and a software bus
//                  read observe the same value.
//   sw_read()   -- the software bus read: read_val() followed by the read-to-clear
//                  side effect (rclr_mask). ONLY a genuine bus access lands here.
//   write_val() -- a software write: masked by sw_wmask, then fires write observers.
interface class fw_reg_val_if #(int W = 32);
    pure virtual function bit [W-1:0] read_val();
    pure virtual function bit [W-1:0] sw_read();
    pure virtual task                 write_val(input bit [W-1:0] v);
endclass
