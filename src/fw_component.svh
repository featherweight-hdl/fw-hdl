
class fw_component;
    protected string          m_name;
    protected fw_component   m_parent;
    protected fw_component   m_children[$];

    function new(string name, fw_component parent);
        m_name = name;
        m_parent = parent;

        if (parent != null) begin
            parent.m_children.push_back(this);
        end
    endfunction

    function void build();
    endfunction

    function void connect();
    endfunction

    task run();
    endtask

    function void do_build();
    endfunction

    function void do_connect();
    endfunction

    task do_run();
    endtask

endclass

