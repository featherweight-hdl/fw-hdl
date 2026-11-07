"""One writer per field, from SV: two components' processes writing the same
field of a shared object is an error at lowering, unless the field declares
(* fw_arbitrate="priority" *). See docs/methodology/timing.md (shared state)."""
import pytest

from zuspec.synth.proc.lower import LowerError

from _elab_helpers import RV1_SV, lower_sv, rv1_top


def design(attr=""):
    return RV1_SV + f'''
package sw_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class shared;
        {attr} bit [7:0] n;
    endclass

    // ticks: n counts cycles
    class ticker extends fw_component implements fw_runnable;
        shared sh;
        function new(string name, fw_component parent, shared sh);
            super.new(name, parent);
            this.sh = sh;
            add_runnable(this);
        endfunction
        virtual task run();
            forever begin
                tick(1);
                sh.n = sh.n + 1;
            end
        endtask
    endclass

    // loads n from each beat, and returns it
    class loader extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) src;
        fw_port #(fw_put_if #(bit [7:0])) dst;
        shared  sh;
        ticker  t;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            dst = new("dst", this);
            sh  = new();
            t   = new("t", this, sh);
        endfunction
        virtual task run();
            bit [7:0] x;
            forever begin
                src.t.get(x);
                sh.n = x;
                dst.t.put(sh.n);
            end
        endtask
    endclass
endpackage
''' + rv1_top("sw_top", "loader", {"src": "bit [7:0]"}, {"dst": "bit [7:0]"}, imports=["sw_pkg"])


def test_two_processes_writing_a_field_is_an_error(tmp_path):
    with pytest.raises(LowerError, match=r"bits 7:0 are written by .* in the same cycle"):
        lower_sv(design(), "sw_top", tmp_path)


def test_declared_arbitration_lowers(tmp_path):
    low = lower_sv(design('(* fw_arbitrate="priority" *)'), "sw_top", tmp_path)
    assert any("fw_arbitrate=priority" in l for l in low.report)
