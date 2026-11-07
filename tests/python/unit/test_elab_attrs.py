"""fw-hdl directives (``(* fw_* *)`` attributes) reach the process IR: on
fields (Var.attrs), on loops (Loop.attrs), and as timing regions (Region)
round code whose timing context differs from its caller's. A malformed
directive is an error. See docs/methodology/timing.md."""
import pytest

from zuspec.synth.proc import ir as P

from fw.hdl.fe.elab.attrs import AttrError
from _elab_helpers import RV1_SV, lower_sv, rv1_top, translate_sv


def design(fields="", run="", extra=""):
    """A component with a put port on a ready/valid output (a latency-insensitive
    binding), with ``fields`` and a ``run()`` body, plus ``extra`` class
    members."""
    return RV1_SV + f'''
package at_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;

    class at extends fw_component implements fw_runnable;
        fw_port #(fw_put_if #(bit [7:0])) dst;
        bit [7:0] n;
{fields}
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        function void build();
            dst = new("dst", this);
        endfunction
{extra}
        virtual task run();
{run}
        endtask
    endclass
endpackage
''' + rv1_top("at_top", "at", {}, {"dst": "bit [7:0]"}, imports=["at_pkg"])


PLAIN = "            forever begin dst.t.put(n); n = n + 1; end"


def run_proc(st):
    return next(p for p in st.design.procs if p.name == "root_run")


def walk(stmts, depth=0):
    """(depth, stmt) over a statement tree, into regions, ifs and loops."""
    for s in stmts:
        yield depth, s
        if isinstance(s, P.Region):
            yield from walk(s.body, depth + 1)
        elif isinstance(s, P.Loop):
            yield from walk(s.body, depth)
        elif isinstance(s, P.If):
            yield from walk(s.then, depth)
            yield from walk(s.orelse, depth)


def regions(stmts):
    return [(d, s.timed, s.origin) for d, s in walk(stmts) if isinstance(s, P.Region)]


def test_field_attrs_reach_vars(tmp_path):
    st = translate_sv(design(fields='        (* fw_resource="bypass", fw_storage="bram" *) '
                                    'bit [7:0] acc;',
                             run="            forever begin dst.t.put(acc); acc = acc + n; "
                                 "n = n + 1; end"), "at_top", tmp_path)
    acc = next(v for v in st.design.vars if v.origin.endswith(".acc"))
    assert acc.attrs == {"fw_resource": "bypass", "fw_storage": "bram"}
    n = next(v for v in st.design.vars if v.origin.endswith(".n"))
    assert n.attrs == {}


def test_loop_attrs_reach_loops(tmp_path):
    st = translate_sv(design(run="            (* fw_ii=2 *)\n" + PLAIN), "at_top", tmp_path)
    # (the transactor's own wait loop is inside the timed region)
    loops = [s for d, s in walk(run_proc(st).body) if isinstance(s, P.Loop) and d == 0]
    assert [l.attrs for l in loops] == [{"fw_ii": 2}]
    assert "loop pre=None post=None (* fw_ii=2 *)" in P.dump(st.design)


def test_untimed_run_has_a_timed_region_per_port_call(tmp_path):
    st = translate_sv(design(run=PLAIN), "at_top", tmp_path)
    # run() is untimed; the bridge holds a virtual interface, so it is timed
    assert regions(run_proc(st).body) == [(0, True, "rv1_put_x.put")]


def test_timed_untimed_timed_nesting(tmp_path):
    extra = '''
        (* fw_timed, fw_latency_insensitive *)
        task t_outer();
            n = n + 1;
            u_inner();
        endtask
        task u_inner();
            dst.t.put(n);
        endtask'''
    st = translate_sv(design(run="            forever t_outer();", extra=extra), "at_top", tmp_path)
    assert regions(run_proc(st).body) == [(0, True, "at.t_outer"), (1, False, "at.u_inner"),
                                          (2, True, "rv1_put_x.put")]


def test_timed_class_marks_its_tasks(tmp_path):
    text = design(run=PLAIN).replace("    class at extends", "    (* fw_timed *)\n    class at extends")
    st = translate_sv(text, "at_top", tmp_path)
    # run() is timed, and so is everything it calls: no region changes the
    # timing context; the one left marks the call to another object (put)
    rs = [s for _, s in walk(run_proc(st).body) if isinstance(s, P.Region)]
    assert [(r.timed, r.call, r.site.recv, r.site.method) for r in rs] == \
        [(True, "", "dst.t", "put")]


def test_regions_lower_as_written(tmp_path):
    low = lower_sv(design(run=PLAIN), "at_top", tmp_path)
    assert any(l.startswith("root_run: ") for l in low.report)


@pytest.mark.parametrize("attr, where, msg", [
    ("(* fw_bogus *)", "field", "unknown fw-hdl directive fw_bogus"),
    ("(* fw_ii=0 *)", "loop", "fw_ii takes a positive integer"),
    ('(* fw_ii="fast" *)', "loop", "fw_ii takes a positive integer"),
    ('(* fw_resource="maybe" *)', "field", 'fw_resource="maybe": one of stall, bypass'),
    ("(* fw_resource=1 *)", "field", "fw_resource takes a string"),
    ("(* fw_ii=2 *)", "field", "fw_ii does not apply to a field"),
    ("(* fw_timed=0 *)", "task", "fw_timed is a flag"),
])
def test_malformed_directives_are_errors(tmp_path, attr, where, msg):
    if where == "field":
        text = design(fields=f"        {attr} bit [7:0] acc;",
                      run="            forever begin dst.t.put(acc); acc = acc + 1; end")
    elif where == "loop":
        text = design(run=f"            {attr}\n" + PLAIN)
    else:
        text = design(run="            forever t();",
                      extra=f"        {attr}\n        task t(); dst.t.put(n); endtask")
    with pytest.raises(AttrError, match=msg):
        translate_sv(text, "at_top", tmp_path)


def test_other_attributes_are_ignored(tmp_path):
    st = translate_sv(design(fields="        (* keep, mark_debug=\"true\" *) bit [7:0] acc;",
                             run="            forever begin dst.t.put(acc); acc = acc + 1; end"),
                      "at_top", tmp_path)
    acc = next(v for v in st.design.vars if v.origin.endswith(".acc"))
    assert acc.attrs == {}
