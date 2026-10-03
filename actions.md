
# Actions
Actions are closures around behaviors. The capture data and resources required
by the behavior and results. An action's lifecycle is:

- bind/connect to resources
  - Ensure all inputs are available
  - Ensure all resources are available
    - Allow resources to be claimed based on input values
  - Run 'body'

# Buffer Pools
Buffer pools provide buffer-claim data. Buffer-pool input claims
must be connected to a buffer-provider interface:
- provider.get(self, qualifiers())

```systemverilog
interface class action_body_if;
  pure virtual task body();
endclass

interface class action_impl_if;
  pure virtual function action_if parent();
  pure virtual function std::process thread();
endclass

interface class activity_ctxt_if;
  pure virtual function enter();
  pure virtual function leave();

endclass

interface class action_if;
  pure virtual task traverse(activity_ctxt_if parent);
endclass

interface class buffer_provider_if #(type Tbuffer);
endclass

class buffer_in #(type Tbuffer=int, type Taction=int);
  buffer_provider_if #(Tbuffer) m_peer;
  function new(string name, Taction parent);
    super.new(name, parent);
  endfunction

  function Taction b(buffer_provider_if #(Tbuffer) p);
    // TODO: connect in the producer to use
    return m_action;
  endfunction
endclass

class buffer_out #(type Tbuffer=int, type Taction=int);
  mailbox #(Tbuffer) m_mb;

  function void put(Tbuffer v);
    m_action.notify();
  endfunction

  function Taction b(buffer_in #(Tbuffer) in);
  endfunction
  
  
endclass

class action_c implements action_if, action_body_if;
  task traverse(activity_ctxt_if parent);
    // To binding
  endtask

  task do_bind();
    // Wait for inputs, but 
    foreach (i : buffer_in) begin
      if (!i.bound()) begin
        if (i.do_bind()) begin
        end
      end
    end

    foreach (c: claims) begin
      if (!c.bound()) begin
        if (c.do_bind()) begin
        end
      end
    end

  endtask

  task do_publish();
    foreach (o : buffer_out) begin
      o.do_publish();
    end

  endtask

endclass

class my_producer;
  buffer_in #(buffer_t, my_producer)   in;
  buffer_out #(buffer_t, my_producer)  out;

  function new(string name, fw_component parent);
    super.new(name, parent);

    in = new("in", this);
    out = new("out", this);

  endfunction

endclass

```

- PoolCAM
- PoolFIFO - provider policy (?)


 