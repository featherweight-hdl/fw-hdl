// A put that never blocks: valid-only flow control. put(t) is a function, so a
// caller cannot wait on it; the receiver must always have room, which a credit
// scheme guarantees. In RTL the port has data and valid and no ready.
// fw_valid_channel reports a put while full as a credit violation.
interface class fw_valid_put_if #(type T);
    pure virtual function void put(input T t);
endclass
