"""The pin shell (fw.hdl.emit.pins, plan S6.1c3): a role-port member with
``(* fw_pins = "<preset>" *)`` gives module ``<var>_pins`` with one pin per
payload struct member, ``<preset><ch><member>``; a ``fw_opt`` member whose
parameter is 0 is no pin (tied to 0 on an input, dropped on an output)."""
from __future__ import annotations

import pytest

from fw.hdl.emit.sync import emit_sync
from fw.hdl.fe.elab.sync import SyncElabError

SV = '''
package mini_proto_pkg;
    typedef enum bit { FW_FWD = 1'b0, FW_REV = 1'b1 } fw_dir_e;
    typedef struct packed { int unsigned HAS_X; int unsigned W; } prm_t;

    class mini_types #(prm_t P = '{HAS_X: 1, W: 8});
        typedef struct packed {
            bit [P.W-1:0] addr;
            (* fw_opt = "HAS_X" *) bit [3:0] x;
            bit [2:0] len;
        } q_t;
        typedef struct packed { bit [15:0] data; bit last; } p_t;
    endclass

    virtual class sp_base;
        function new(string name, int unsigned role);
        endfunction
    endclass

    class fw_rv_ch #(type T = logic);
        static function void add_ctl(sp_base sp, string ch, fw_dir_e dir);
        endfunction
    endclass

    virtual class mini_sp #(prm_t P) extends sp_base;
        function new(string name, int unsigned role);
            super.new(name, role);
            fw_rv_ch #(mini_types #(P)::q_t)::add_ctl(this, "q", FW_FWD);
            fw_rv_ch #(mini_types #(P)::p_t)::add_ctl(this, "p", FW_REV);
        endfunction
    endclass

    class mini_mgr_sp #(prm_t P) extends mini_sp #(P);
        fw_hdl_pkg::fw_rv_sig #(mini_types #(P)::q_t) q;
        fw_hdl_pkg::fw_rv_sig #(mini_types #(P)::p_t) p;
        function new(string name);
            super.new(name, 0);
        endfunction
    endclass

    class mini_sub_sp #(prm_t P) extends mini_sp #(P);
        fw_hdl_pkg::fw_rv_sig #(mini_types #(P)::q_t) q;
        fw_hdl_pkg::fw_rv_sig #(mini_types #(P)::p_t) p;
        function new(string name);
            super.new(name, 1);
        endfunction
    endclass
endpackage

class role_pass #(mini_proto_pkg::prm_t P = '{HAS_X: 1, W: 8}) extends fw_hdl_pkg::fw_component;
    (* fw_pins = "s_mp_" *) mini_proto_pkg::mini_sub_sp #(P) s;
    mini_proto_pkg::mini_mgr_sp #(P) m;
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

class plain extends fw_hdl_pkg::fw_component;
    (* fw_pins = "x_" *) bit [3:0] v;
    function new(string name, fw_hdl_pkg::fw_component parent);
        super.new(name, parent);
    endfunction
    virtual function void step();
        v = v + 1;
    endfunction
endclass

module t;
    role_pass #('{HAS_X: 1, W: 8}) with_x;
    role_pass #('{HAS_X: 0, W: 6}) no_x;
    plain bad;
endmodule
'''


@pytest.fixture(scope="module")
def top(tmp_path_factory):
    f = tmp_path_factory.mktemp("emit_pins") / "t.sv"
    f.write_text(SV)
    return str(f)


def test_pins_present(top):
    out = emit_sync([top], "t", vars=["with_x"])
    assert list(out) == ["with_x", "with_x_pins"]
    sh = out["with_x_pins"]
    for decl in ("input logic s_mp_qvalid", "output logic s_mp_qready",
                 "input logic [7:0] s_mp_qaddr", "input logic [3:0] s_mp_qx",
                 "input logic [2:0] s_mp_qlen", "output logic [15:0] s_mp_pdata",
                 "output logic s_mp_plast", "output logic m_qvalid"):
        assert decl in sh, decl
    assert ".s_qdata({s_mp_qaddr, s_mp_qx, s_mp_qlen})" in sh
    assert "assign s_mp_pdata = s_pdata__w[16:1];" in sh
    assert "assign s_mp_plast = s_pdata__w[0:0];" in sh
    assert ".m_qdata(m_qdata)" in sh


def test_pins_absent_member(top):
    sh = emit_sync([top], "t", vars=["no_x"])["no_x_pins"]
    assert "s_mp_qx" not in sh
    assert "input logic [5:0] s_mp_qaddr" in sh
    assert ".s_qdata({s_mp_qaddr, 4'd0, s_mp_qlen})" in sh


def test_pins_not_a_role_port(top):
    with pytest.raises(SyncElabError, match="not a role port"):
        emit_sync([top], "t", vars=["bad"])
