"""Partition (fe/elab/hier.py) records each instance's clock and reset domain
and rejects, at the SV line that bound it, what its single-clock,
single-reset lowering cannot do (design-domains.md §7.5): a clock domain
unrelated to the root's, and a reset domain other than the root's."""
import re

import pytest

from fw.hdl.errors import FwHdlError
from fw.hdl.xls_flow import sv_to_structure

PKG = """
package pdom_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    // A second root clock domain (nothing drives it here).
    class clk2 extends fw_export #(fw_clock_domain_if) implements fw_clock_domain_if;
        function new(string name, fw_component parent);
            super.new(name, parent, this);
        endfunction
        virtual task tick(int n = 1); endtask
        virtual function longint root_ticks(int n = 1); return n; endfunction
        virtual function fw_domain_kind_e domain_kind(); return FW_DOMAIN_CLOCK; endfunction
        virtual function string domain_name(); return full_name(); endfunction
        virtual function int domain_nsrc(); return 0; endfunction
        virtual function fw_domain_if domain_src(int i); return null; endfunction
        virtual function fw_domain_if domain_equiv(); return this; endfunction
    endclass

    class leaf extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
        endfunction
        virtual task run();
            forever begin bit [7:0] x; in.t.get(x); out.t.put(x); end
        endtask
    endclass

    class top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        leaf a, b;
        fw_channel #(bit [7:0], 1) ch;
        fw_clock_domain div2;
        clk2 c2;
        fw_reset_combine srst;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            a = new("a", this);
            b = new("b", this);
            ch = new("ch", this);
            div2 = new("div2", this, 2);
            c2 = new("c2", this);
            srst = new("srst", this, 2);
        endfunction
        function void connect();
            a.in.connect(in);
            b.out.connect(out);
            a.out.connect(ch.put_ex);
            b.in.connect(ch.get_ex);
            div2.src.connect(this.clock);
            srst.src[0].connect(this.reset);
            srst.src[1].connect(this.reset);
@@CONNECT@@
        endfunction
    endclass
endpackage
"""

CASES = [
    ("root_domains", "", None),
    ("divided_clock", "            b.clock.connect(div2);", None),
    ("second_clock", "            b.clock.connect(c2);  // HERE",
     r"top\.b: clock domain top\.c2 is unrelated to the root clock"),
    ("derived_reset", "            b.reset.connect(srst);  // HERE",
     r"top\.b: reset domain top\.srst is not the root's; derived reset domains are not "
     r"lowered by Partition yet"),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_partition_domains(tmp_path, case):
    _, connect, msg = case
    text = PKG.replace("@@CONNECT@@", connect)
    path = tmp_path / "pdom_pkg.sv"
    path.write_text(text)
    if msg is None:
        sv_to_structure([str(path)], "top")
        return
    with pytest.raises(FwHdlError) as ex:
        sv_to_structure([str(path)], "top")
    assert re.search(msg, str(ex.value)), str(ex.value)
    line = next(i + 1 for i, l in enumerate(text.splitlines()) if "// HERE" in l)
    m = re.search(r"pdom_pkg\.sv:(\d+):\d+", str(ex.value))
    assert m and int(m.group(1)) == line, str(ex.value)
