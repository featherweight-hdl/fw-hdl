// A put port that an all-or-nothing step (fw_atomic_step) may also use.
// put_or_stall(t) puts t if the output had space at the start of the cycle;
// otherwise the whole step has no effect this cycle (fw_steppable.svh). It
// returns nothing, so the step cannot branch on readiness: XLS cannot either.
// fw-hdl lowers it to a blocking send.
interface class fw_put_step_if #(type T) extends fw_put_if #(T);
    pure virtual function void put_or_stall(input T t);
endclass
