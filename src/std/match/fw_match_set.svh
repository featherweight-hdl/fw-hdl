// fw_match_set -- is a value one of a set: equality over the valid slots.
//
//   keys   K slots of type T, packed (slot i is keys[i]);
//   valid  bit i: slot i holds a member of the set;
//   q      the value looked up.
//
//   hits   bit i is set when slot i is valid and holds q;
//   any    q is in the set (the OR of hits);
//   first  the lowest slot that hits; 0 when none does, so read it with any.
//
// Static functions: the caller owns the set (in its state, or from a table)
// and calls these in its own step(), so the match adds no cycle and no
// channel. They are pure; each specialization is one function in the IR,
// invoked by the caller. An invalid slot never hits, whatever it holds, and
// a value held by several slots hits each of them.
class fw_match_set #(int K = 8, type T = bit [15:0]);
    localparam int IB = (K > 1) ? $clog2(K) : 1;

    static function bit [K-1:0] hits(T [K-1:0] keys, bit [K-1:0] valid, T q);
        bit [K-1:0] h;
        for (int i = 0; i < K; i++)
            h[i] = valid[i] && keys[i] == q;
        return h;
    endfunction

    static function bit any(T [K-1:0] keys, bit [K-1:0] valid, T q);
        return |hits(keys, valid, q);
    endfunction

    static function bit [IB-1:0] first(T [K-1:0] keys, bit [K-1:0] valid, T q);
        // The lowest hit alone (a hit with no hit below it; "below" is an OR
        // over doubling shifts, log K deep), then its index as an OR of
        // indices. A loop of selects from slot to slot would be K deep.
        bit [K-1:0] h = hits(keys, valid, q);
        bit [K-1:0] below = h << 1;
        bit [K-1:0] oh;
        bit [IB-1:0] f;
        for (int s = 1; s < K; s <<= 1)
            below |= below << s;
        oh = h & ~below;
        for (int i = 0; i < K; i++)
            f |= oh[i] ? IB'(i) : '0;
        return f;
    endfunction
endclass
