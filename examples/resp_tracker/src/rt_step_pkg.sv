// The response-tracker reference design, stage 1, in cycle-step form: the
// same two blocks and queue as rt_pkg.sv, each block an fw_steppable whose
// step() is one clock cycle.
//
//   req ──► rt_tag ──q (RT_Q_DEPTH)──► rt_resp ──► rsp
//
// Each cycle rt_tag polls for a request and, when one arrives, sends it on
// with the next tag; rt_resp polls the queue and answers what it finds with
// {tag, 3 * addr}. A step never waits, so its outputs are valid-only: the
// queue is an fw_valid_channel, which rt_resp drains every cycle, and rsp
// has no back-pressure. Responses leave in request order, as in rt_pkg.sv,
// and every knob set gives the same latency.
package rt_step_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    import rt_top_knobs_pkg::*;

    typedef bit [7:0]  req_t;       // address
    typedef bit [11:0] tagged_t;    // {tag[3:0], address}
    typedef bit [15:0] rsp_t;       // {tag[3:0], data[11:0]}

    class rt_tag extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(req_t))       in;
        fw_port #(fw_valid_put_if #(tagged_t)) out;
        bit [3:0] tag;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual function void step();
            req_t a;
            if (in.t.try_get(a)) begin
                out.t.put({tag, a});
                tag = tag + 4'd1;
            end
        endfunction
    endclass

    class rt_resp extends fw_component implements fw_steppable;
        fw_port #(fw_get_nb_if #(tagged_t)) in;
        fw_port #(fw_valid_put_if #(rsp_t)) out;

        function new(string name, fw_component parent);
            super.new(name, parent);
            add_steppable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual function void step();
            tagged_t t;
            bit [11:0] d;
            if (in.t.try_get(t)) begin
                d = 12'(t[7:0]) * 12'd3;
                out.t.put({t[11:8], d});
            end
        endfunction
    endclass

    class rt_top extends fw_component;
        fw_port #(fw_get_nb_if #(req_t))    req;
        fw_port #(fw_valid_put_if #(rsp_t)) rsp;
        rt_tag                                   tagger;
        rt_resp                                  responder;
        fw_valid_channel #(tagged_t, RT_Q_DEPTH) q;

        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            req = new("req", this);
            rsp = new("rsp", this);
            tagger = new("tagger", this);
            responder = new("responder", this);
            q = new("q", this);
        endfunction
        function void connect();
            tagger.in.connect(req);
            tagger.out.connect(q.put_ex);
            responder.in.connect(q.get_nb_ex);
            responder.out.connect(rsp);
        endfunction
    endclass
endpackage
