
class cag_risc_c extends fw_component;
  // TLM port for 
  state_c #(bit[31:0])   pc;
  resource_pool_c #(bit[31:0]) regs;
  mem_if ifetch;

  class fetch_a extends fw_action;
    buffer_out #(bit[31:0]) out;
    state_in #(bit[31:0]) pc;

    task body();
        comp.ifetch.read(pc.t, out.t);
    endtask
    
  endclass

  class decode_a extends fw_action;
    rand buffer_in #(bit[31:0]) in;
    rand buffer_out #(decode_data_t) out;
    rand resource_share #(bit[31:0]) rs1;
    rand resource_share #(bit[31:0]) rs2;

    constraint io_c {
        out.rd == in.t[3:0];
        out.rd == in.t[3:0];
    }
  endclass

  task run();
    forever begin
        fetch_a fetch = new();
        decode_a decode = new();

        fetch.traverse(this);
        decode.in.b(fetch.out).traverse(this);

    end
  endtask

endclass