// fw_keyed_table -- a table of up to N entries, each a unique key and a value.
//
//   ins      {key, value}: install (fw_get_nb_if);
//   ins_rsp  {ok, full, slot}: ok and the slot taken, or why not
//            (fw_put_step_if);
//   lkp      key: look up (fw_get_nb_if);
//   lkp_rsp  {hit, slot, value} (fw_put_step_if);
//   wr       {slot, value}: write a live slot's value (fw_get_nb_if);
//   rm       slot: free a live slot (fw_get_nb_if).
//
// Install and lookup return a slot; write and remove name one, so only
// install and lookup match keys. Each port takes at most one request per
// cycle, so a cycle can do one of each.
//
// Per cycle:
//   observes  the table at the start of the cycle. Every request sees that
//             state and never another request's effect from the same cycle,
//             so the cycle is the same as lookup, install, write, remove done
//             one after another (the order the contract checks): a lookup
//             gets the value from before a same-cycle write, a key installed
//             this cycle misses a same-cycle lookup, and a slot removed this
//             cycle is free from the next;
//   install   refused if the key is live (ok = 0, full = 0), else if no slot
//             is free (ok = 0, full = 1); else takes the lowest free slot.
//             A refusal is a response, not back-pressure. slot is 0 when
//             refused;
//   lookup    hit, and the matching slot and value; on a miss, slot and value
//             are 0. Keys are unique, so at most one slot matches;
//   misuse    a write or remove that names a slot free at the start of the
//             cycle has no effect;
//   back-pressure  stalls the whole table: if ins_rsp or lkp_rsp is not
//             ready, no request is taken and nothing changes. A user whose
//             install and lookup paths must not wait on each other puts an
//             fw_channel (DEPTH 2) on each response.
//
// The class is an all-or-nothing step (fw_atomic_step), so the model is
// cycle-exact and step() is what fw-hdl lowers. Every match is a mask over
// the slots, the lowest free slot is the lowest set bit of the free mask, and
// each slot's next state is chosen from those masks, so the cycle's logic is
// a few levels deep for any N.
// Its state is one packed struct, zero (empty) at reset.

// fw_keyed_table's state (a class only to carry the parameters).
class fw_keyed_table_state #(type K = bit [7:0], type V = bit [7:0], int N = 16);
    typedef struct packed {
        bit [N-1:0] vld;        // slot k is live
        K [N-1:0]   key;
        V [N-1:0]   val;
    } t;
endclass

class fw_keyed_table #(type K = bit [7:0], type V = bit [7:0], int N = 16)
        extends fw_atomic_step #(fw_keyed_table_state #(K, V, N)::t);
    localparam int KW = $bits(K);
    localparam int VW = $bits(V);
    localparam int SB = (N > 1) ? $clog2(N) : 1;
    fw_port #(fw_get_nb_if #(bit [KW+VW-1:0]))   ins;
    fw_port #(fw_put_step_if #(bit [SB+1:0]))     ins_rsp;
    fw_port #(fw_get_nb_if #(K))                  lkp;
    fw_port #(fw_put_step_if #(bit [SB+VW:0]))    lkp_rsp;
    fw_port #(fw_get_nb_if #(bit [SB+VW-1:0]))   wr;
    fw_port #(fw_get_nb_if #(bit [SB-1:0]))       rm;

    function new(string name, fw_component parent);
        super.new(name, parent);
    endfunction

    function void build();
        ins = new("ins", this);
        ins_rsp = new("ins_rsp", this);
        lkp = new("lkp", this);
        lkp_rsp = new("lkp_rsp", this);
        wr = new("wr", this);
        rm = new("rm", this);
    endfunction

    // Every request reads the table at the start of the cycle. The update is
    // per slot: masks say which slot install, write and remove name, and each
    // slot's next live bit, key and value are chosen from them, so no store
    // depends on another.
    virtual function void step();
        bit [N-1:0]       live, m, fr, oh, im, wm, rmm;
        K                 k, ik;
        V                 v, iv_v, wv_v;
        bit [KW+VW-1:0]   iv;
        bit [SB+VW-1:0]   wv;
        bit [SB-1:0]      sl, r;
        bit               ok, dup, wok, rok;
        K [N-1:0]         nk;
        V [N-1:0]         nv;
        live = s.vld;
        if (lkp.t.try_get(k)) begin
            for (int i = 0; i < N; i++)
                m[i] = live[i] && s.key[i] == k;
            sl = '0;
            v = '0;
            for (int i = 0; i < N; i++) begin
                sl = sl | (m[i] ? SB'(i) : SB'(0));
                v = v | (m[i] ? s.val[i] : V'(0));
            end
            lkp_rsp.t.put_or_stall({|m, sl, v});
        end
        if (ins.t.try_get(iv)) begin
            ik = K'(iv[KW+VW-1:VW]);
            iv_v = V'(iv[VW-1:0]);
            for (int i = 0; i < N; i++)
                m[i] = live[i] && s.key[i] == ik;
            dup = |m;
            // The lowest free slot: fr less every slot above a free one
            // (a prefix OR in log2(N) steps, not an N-bit carry chain).
            fr = ~live;
            m = fr;
            for (int j = 0; j < SB; j++)
                m = m | (m << (1 << j));
            oh = fr & ~(m << 1);
            sl = '0;
            for (int i = 0; i < N; i++)
                sl = sl | (oh[i] ? SB'(i) : SB'(0));
            ok = !dup && |fr;
            im = ok ? oh : '0;
            ins_rsp.t.put_or_stall({ok, !dup && !(|fr), ok ? sl : SB'(0)});
        end
        wok = wr.t.try_get(wv);
        wv_v = V'(wv[VW-1:0]);
        rok = rm.t.try_get(r);
        for (int i = 0; i < N; i++) begin
            wm[i] = wok && live[i] && wv[SB+VW-1:VW] == SB'(i);
            rmm[i] = rok && live[i] && r == SB'(i);
        end
        for (int i = 0; i < N; i++) begin
            nk[i] = im[i] ? ik : s.key[i];
            nv[i] = wm[i] ? wv_v : (im[i] ? iv_v : s.val[i]);
        end
        s.vld = (live | im) & ~rmm;
        s.key = nk;
        s.val = nv;
    endfunction
endclass
