"""FE-12 / P10: constructs outside the static subset are rejected with one
diagnostic that points at the SV source line (xls-phase0.md §5.3, "Negative")."""
import re

import pytest

from fw.hdl.errors import FwHdlError
from fw.hdl.xls_flow import sv_functions_to_xls, sv_to_xls
from zuspec.be.xls.width import StaticSubsetError

CLASS = """`include "fw_std_macros.svh"
package neg_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
    class neg extends fw_component implements fw_runnable;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        bit [7:0] acc;
        function new(string name, fw_component parent);
            super.new(name, parent);
            add_runnable(this);
        endfunction
        virtual task run();
@@RUN@@
        endtask
@@MEMBERS@@
    endclass
endpackage
"""
RUN_LINE = 14       # the first line of @@RUN@@


def write(tmp_path, run, members=""):
    p = tmp_path / "neg_pkg.sv"
    p.write_text(CLASS.replace("@@RUN@@", run).replace("@@MEMBERS@@", members))
    return str(p)


def located(exc) -> int:
    m = re.search(r"neg_pkg\.sv:(\d+):\d+", str(exc))
    assert m, f"diagnostic has no location: {exc}"
    return int(m.group(1))


CASES = [
    # (id, run body, members, error type, message regex, line offset in run)
    ("p10_get_in_loop",
     "            forever begin\n"
     "                bit [7:0] x;\n"
     "                for (int i = 0; i < 4; i++) in.t.get(x);\n"
     "            end",
     "", StaticSubsetError, r"inside a loop.*one iteration per activation", 2),
    ("p10_second_get",
     "            forever begin\n"
     "                bit [7:0] x, y;\n"
     "                in.t.get(x);\n"
     "                in.t.get(y);\n"
     "                out.t.put(x + y);\n"
     "            end",
     "", StaticSubsetError, r"second operation on channel 'in'", 3),
    ("p10_tick",
     "            forever begin\n"
     "                tick();\n"
     "            end",
     "", FwHdlError, r"task 'tick'", 1),
    ("p10_delay",
     "            forever begin\n"
     "                #5;\n"
     "            end",
     "", FwHdlError, r"timing controls", 1),
    ("p1_no_forever",
     "            bit [7:0] x;\n"
     "            in.t.get(x);",
     "", StaticSubsetError, r"must end in `forever`", None),
    ("d1_unguarded_divide",
     "            forever begin\n"
     "                bit [7:0] x;\n"
     "                in.t.get(x);\n"
     "                out.t.put(acc / x);\n"
     "            end",
     "", StaticSubsetError, r"may be zero", 3),
    ("t2_four_state",
     "            forever begin\n"
     "                logic [7:0] x;\n"
     "                in.t.get(x);\n"
     "            end",
     "", FwHdlError, r"4-state type", 1),
    ("s5_impure_function",
     "            forever begin\n"
     "                bit [7:0] x;\n"
     "                in.t.get(x);\n"
     "                out.t.put(peek(x));\n"
     "            end",
     "        function bit [7:0] peek(bit [7:0] v);\n"
     "            return v + acc;\n"
     "        endfunction",
     FwHdlError, r"reads class property 'acc'.*pure", None),
    ("x0_break",
     "            forever begin\n"
     "                bit [7:0] x;\n"
     "                in.t.get(x);\n"
     "                for (int i = 0; i < 4; i++) if (x[i]) break;\n"
     "            end",
     "", FwHdlError, r"break/continue", 3),
    ("x0_casez",
     "            forever begin\n"
     "                bit [7:0] x;\n"
     "                in.t.get(x);\n"
     "                casez (x) 8'b1???????: acc = 1; default: acc = 0; endcase\n"
     "            end",
     "", FwHdlError, r"casez", 3),
    ("x0_nonblocking",
     "            forever begin\n"
     "                bit [7:0] x;\n"
     "                in.t.get(x);\n"
     "                acc <= x;\n"
     "            end",
     "", FwHdlError, r"non-blocking", 3),
]


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_rejected(tmp_path, case):
    _, run, members, exc_t, msg, offset = case
    path = write(tmp_path, run, members)
    with pytest.raises(exc_t) as ex:
        sv_to_xls([path], "neg")
    assert re.search(msg, str(ex.value), re.S), str(ex.value)
    if offset is not None:
        assert located(ex.value) == RUN_LINE + offset, str(ex.value)
    else:
        located(ex.value)


def test_function_output_argument(tmp_path):
    p = tmp_path / "fo_pkg.sv"
    p.write_text("""package fo_pkg;
    function automatic bit [7:0] g(bit [7:0] a, output bit [7:0] b);
        b = a;
        return a;
    endfunction
    function automatic bit [7:0] f(bit [7:0] a);
        bit [7:0] t;
        return g(a, t);
    endfunction
endpackage
""")
    with pytest.raises(FwHdlError, match="output argument") as ex:
        sv_functions_to_xls([str(p)], ["f"])
    assert re.search(r"fo_pkg\.sv:8:", str(ex.value))
