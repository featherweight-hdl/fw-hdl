"""Reset domains in the front end (design-domains.md §8): a component's
``reset`` port is seated on the root reset domain like ``clock``, a model that
reads it lowers to a read of the design reset, and ``reset`` is not taken for a
design port."""
import pytest

from _elab_helpers import RV1_SV, rv1_top, translate_sv, lower_sv


def comp(run, extra=""):
    return RV1_SV + f'''
package rd_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class rdc extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) src;
        fw_port #(fw_put_if #(bit [7:0])) dst;
        bit [7:0] n;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            src = new("src", this);
            dst = new("dst", this);
        endfunction
{extra}
        virtual task run();
{run}
        endtask
    endclass
endpackage
''' + rv1_top("rd_top", "rdc", {"src": "bit [7:0]"}, {"dst": "bit [7:0]"}, imports=["rd_pkg"])


RUN = """            wait_reset_deassert();
            forever begin
                src.t.get(n);
                if (in_reset()) n = 8'h00;
                dst.t.put(n);
            end"""


def test_root_reset_is_seated(tmp_path):
    st = translate_sv(comp(RUN), "rd_top", tmp_path)
    root = st.elab.root
    it = st.elab.interp
    names = {m.name: v for m, v in root.fields.items() if hasattr(m, "name")}
    rp = names["reset"]
    prov = next(v for m, v in rp.fields.items() if getattr(m, "name", "") == "m_provider")
    assert prov is not None and prov.cls.name == "fw_reset_xtor_bridge"


def _src(d, name):
    """Follow plain net assigns from *name* to its source variable."""
    val = {a.var.name: a.value for a in d.assigns}
    seen = set()
    while name in val and name not in seen:
        seen.add(name)
        t = val[name]
        if getattr(t, "op", None) != "var":
            return None
        name = t.name
    return name


def test_in_reset_reads_the_design_reset(tmp_path):
    st = translate_sv(comp(RUN), "rd_top", tmp_path)
    d = st.design
    run = str(next(p for p in d.procs if p.name == "root_run").body)
    # in_reset() -> fw_reset_xtor_bridge -> fw_reset_xtor_if: a read of the
    # root reset transactor's pin, which is the design reset
    assert "value=u_root_u_rst_reset" in run
    assert _src(d, "u_root_u_rst_reset") == d.reset.name == "reset"
    # ...and the whole thing lowers
    low = lower_sv(comp(RUN), "rd_top", tmp_path / "low")
    assert low.verilog


def test_hier_does_not_take_reset_for_a_port(tmp_path):
    from fw.hdl.fe.elab import hier
    st = translate_sv(comp(RUN), "rd_top", tmp_path)
    cls = st.elab.root.cls
    # the user class (rdc), not the root binder
    while cls.name != "rdc":
        cls = cls.baseClass.canonicalType
    node = hier.elaborate_tree(st.elab.interp.comp, cls, "rdc")
    assert set(node.ports) == {"src", "dst"}


# A component in a reset domain other than the root's is supervised: its run()
# restarts with the domain (design-domains.md §4.5). Lowering that is not built,
# so the front end rejects it by name.
SUP_EXTRA = """
        class lvl_rst extends fw_export #(fw_reset_domain_if) implements fw_reset_domain_if;
            bit level;
            function new(string name, fw_component parent);
                super.new(name, parent, this);
            endfunction
            virtual function bit in_reset(); return level; endfunction
            virtual task wait_assert(); endtask
            virtual task wait_deassert(); endtask
            virtual function bit is_async(); return 0; endfunction
            virtual function fw_clock_domain_if sync_clock(); return null; endfunction
            virtual function fw_domain_kind_e domain_kind(); return FW_DOMAIN_RESET; endfunction
            virtual function string domain_name(); return full_name(); endfunction
            virtual function int domain_nsrc(); return 0; endfunction
            virtual function fw_domain_if domain_src(int i); return null; endfunction
            virtual function fw_domain_if domain_equiv(); return this; endfunction
        endclass
"""


def sup_design():
    text = comp(RUN)
    # rdc's child `w` runs in its own reset domain
    text = text.replace("    class rdc extends fw_component implements fw_runnable;",
                        SUP_EXTRA + """
    class wkr extends fw_component implements fw_runnable;
        int n;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        virtual task run(); forever begin tick(); n++; end endtask
    endclass

    class rdc extends fw_component implements fw_runnable;
        wkr w;
        lvl_rst wr;""")
    text = text.replace("""            dst = new("dst", this);
        endfunction""", """            dst = new("dst", this);
            w = new("w", this);
            wr = new("wr", this);
        endfunction
        function void connect();
            w.reset.connect(wr);
        endfunction""")
    return text


def test_supervised_run_is_rejected(tmp_path):
    from fw.hdl.fe.elab.interp import ElabError
    from fw.hdl.fe.elab.translate import TranslateError
    with pytest.raises((ElabError, TranslateError), match=r"w.*reset domain.*wr"):
        translate_sv(sup_design(), "rd_top", tmp_path)
