// The base of an all-or-nothing step (fw_atomic_steppable). The class keeps
// all of its state in `s`, one packed struct S, so the runtime can put it back
// after a stall:
//
//     typedef struct packed { bit [N-1:0] hv; T [N-1:0] hold; } my_state_t;
//     class my_arb extends fw_atomic_step #(my_state_t);
//         fw_port #(fw_get_nb_if #(T))   in[N];
//         fw_port #(fw_put_step_if #(T)) out;
//         virtual function void step();
//             ... out.t.put_or_stall(v); s.hv[k] = 0; ...
//         endfunction
//     endclass
//
// Fields outside `s` are not put back, so they must not change in step().
// The constructor registers the step. `s` is zero at reset, in the model and
// in RTL: choose encodings whose reset state is zero.
virtual class fw_atomic_step #(type S = bit) extends fw_component
        implements fw_atomic_steppable;
    protected S s;
    local S     m_saved;

    function new(string name, fw_component parent);
        super.new(name, parent);
        add_steppable(this);
    endfunction

    pure virtual function void step();

    virtual function void step_save();
        m_saved = s;
    endfunction

    virtual function void step_restore();
        s = m_saved;
    endfunction
endclass
