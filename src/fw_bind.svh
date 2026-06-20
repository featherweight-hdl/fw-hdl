
class fw_bind #(type Troot);
    Troot           root;
    std::process    proc;

    virtual function void build(string path);
        root = new(path, null);
    endfunction

    virtual function void connect();
    endfunction

    function void kill();
        proc.kill();
    endfunction

    task run();
        proc = std::process::self;
    endtask

endclass