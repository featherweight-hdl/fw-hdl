"""fw_proto role ports in sync_component (fe/elab/sync.py, plan S6.1c2): a
member whose class has fw_rv_sig channel holders becomes <port>_<ch><field>
ports, directions from the role and the channel. The protocol below has the
shape of a generated one (fw_proto role_sp.sv.j2): a bundle base whose new()
declares each channel with fw_rv_ch #(T)::add_ctl(this, "<ch>", DIR), and one
class per role calling super.new(name, <role>, owner)."""
from __future__ import annotations

import pytest

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.elab.sync import SyncElabError, find_class_var, sync_component
from fw.hdl.fe.parser import Parser
from zuspec.ir.core.data_type import ProcessKind
from zuspec.ir.core.expr import ExprRefField
from zuspec.ir.core.fields import FieldInOut
from zuspec.ir.core.stmt import StmtAssign

SV = '''
package mini_proto_pkg;
    typedef enum bit { FW_FWD = 1'b0, FW_REV = 1'b1 } fw_dir_e;
    typedef struct packed { bit [7:0] addr; bit [2:0] len; } q_t;
    typedef struct packed { bit [15:0] data; bit last; } p_t;

    virtual class sp_base;
        int unsigned m_role;
        function new(string name, int unsigned role);
            m_role = role;
        endfunction
    endclass

    class fw_rv_ch #(type T = logic);
        static function void add_ctl(sp_base sp, string ch, fw_dir_e dir);
        endfunction
    endclass

    virtual class mini_sp extends sp_base;
        function new(string name, int unsigned role);
            super.new(name, role);
            fw_rv_ch #(q_t)::add_ctl(this, "q", FW_FWD);
            fw_rv_ch #(p_t)::add_ctl(this, "p", FW_REV);
        endfunction
    endclass

    class mini_mgr_sp extends mini_sp;
        fw_hdl_pkg::fw_rv_sig #(q_t) q;
        fw_hdl_pkg::fw_rv_sig #(p_t) p;
        function new(string name);
            super.new(name, 0);
            q = new("q");
            p = new("p");
        endfunction
    endclass

    class mini_sub_sp extends mini_sp;
        fw_hdl_pkg::fw_rv_sig #(q_t) q;
        fw_hdl_pkg::fw_rv_sig #(p_t) p;
        function new(string name);
            super.new(name, 1);
            q = new("q");
            p = new("p");
        endfunction
    endclass

    // A channel without add_ctl.
    class bad_sp extends sp_base;
        fw_hdl_pkg::fw_rv_sig #(q_t) x;
        function new(string name);
            super.new(name, 0);
            x = new("x");
        endfunction
    endclass
endpackage

// Comb pass-through: sub port s in, mgr port m out.
class role_pass extends fw_hdl_pkg::fw_component;
    mini_proto_pkg::mini_sub_sp s;
    mini_proto_pkg::mini_mgr_sp m;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void comb();
        m.q.set_valid(s.q.get_valid());
        m.q.set_data(s.q.get_data());
        s.q.set_ready(m.q.get_ready());
        s.p.set_valid(m.p.get_valid());
        s.p.set_data(m.p.get_data());
        m.p.set_ready(s.p.get_ready());
    endfunction
endclass

class role_bad extends fw_hdl_pkg::fw_component;
    mini_proto_pkg::bad_sp s;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void comb();
        s.x.set_valid(1);
    endfunction
endclass

module t;
    role_pass rp;
    role_bad  rb;
endmodule
'''


@pytest.fixture(scope="module")
def parsed(tmp_path_factory):
    d = tmp_path_factory.mktemp("sync_role")
    f = d / "t.sv"
    f.write_text(SV)
    rep = ErrorReporter()
    p = Parser(FlowConfig(incdirs=[], defines={"FW_TRACE_OFF": "1"}, top_module="t"), rep)
    assert p.parse([str(f)], include_root=False), rep.errors()[:5]
    return p        # keeps the compilation alive


def test_role_pass_shape(parsed):
    comp = sync_component(find_class_var(parsed.compilation, "t", "rp"))
    C = ProcessKind.COMB
    shape = {f.name: (f.datatype.bits, "out" if f.is_out else "in", f.drive)
             for f in comp.fields if isinstance(f, FieldInOut)}
    assert shape == {
        # s is the sub side: q (FWD) comes in, p (REV) goes out.
        "s_qvalid": (1, "in", None),  "s_qready": (1, "out", C), "s_qdata": (11, "in", None),
        "s_pvalid": (1, "out", C),    "s_pready": (1, "in", None), "s_pdata": (17, "out", C),
        # m is the mgr side: the opposite.
        "m_qvalid": (1, "out", C),    "m_qready": (1, "in", None), "m_qdata": (11, "out", C),
        "m_pvalid": (1, "in", None),  "m_pready": (1, "out", C), "m_pdata": (17, "in", None),
    }
    assert len(comp.fields) == 12
    names = [f.name for f in comp.fields]
    body = []
    for s in comp.comb_processes[0].body:
        assert isinstance(s, StmtAssign) and isinstance(s.value, ExprRefField)
        body.append(f"{names[s.targets[0].index]} = {names[s.value.index]}")
    assert body == ["m_qvalid = s_qvalid", "m_qdata = s_qdata", "s_qready = m_qready",
                    "s_pvalid = m_pvalid", "s_pdata = m_pdata", "m_pready = s_pready"]


def test_channel_without_direction_is_an_error(parsed):
    with pytest.raises(SyncElabError, match="channel 'x' has no add_ctl direction"):
        sync_component(find_class_var(parsed.compilation, "t", "rb"))
