"""fw-hdl wrap round trip: wrap a module, put the wrapper in a top, and the
integrated RTL works; the cosim skeleton, once its class is set, passes.

fw_rv_fifo and ref_arb3 are used as wrapped. dma_like (tests/xls/wrap/) gets
the edits a person makes after wrapping (facts filled in) first. Running wrap
again over an edited wrapper writes ``.new`` and leaves the edits alone.
"""
import random

import pytest
import yaml

from fw.hdl import wrap
from fw.hdl.spl_flow import partition, spl_to_rtl
from fw.hdl.verif import cosim
from xls_harness import REPO, VERILATOR, rtl_testbench, run_verilator

HERE = REPO / "tests" / "xls"
FIFO = REPO / "src" / "rtl" / "fw_rv_fifo.sv"
ARB = REPO / "tests" / "stdlib" / "cosim" / "ref_arb3.sv"
DMA = HERE / "wrap" / "dma_like.sv"

TOPS = {
    "fifo": """\
    class w_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) in;
        fw_port #(fw_put_if #(bit [7:0])) out;
        fw_rv_fifo_rtl q;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            q = new("q", this);
        endfunction
        function void connect();
            q.in.connect(in);
            q.out.connect(out);
        endfunction
    endclass
""",
    "arb": """\
    class w_top extends fw_component;
        fw_port #(fw_get_if #(bit [7:0])) a, b, c;
        fw_port #(fw_put_if #(bit [9:0])) out;
        ref_arb3_rtl arb;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            a = new("a", this);
            b = new("b", this);
            c = new("c", this);
            out = new("out", this);
            arb = new("arb", this);
        endfunction
        function void connect();
            arb.req[0].connect(a);
            arb.req[1].connect(b);
            arb.req[2].connect(c);
            arb.gnt.connect(out);
        endfunction
    endclass
""",
    "dma": """\
    class w_top extends fw_component;
        fw_port #(fw_get_if #(bit [15:0])) cmd;
        fw_port #(fw_valid_put_if #(bit [7:0])) done;
        fw_port #(fw_level_if #(bit)) cfg_en;
        fw_port #(fw_level_if #(bit [2:0])) cfg_burst;
        fw_port #(fw_level_set_if #(bit)) status_busy;
        dma_like_rtl dma;
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            cmd = new("cmd", this);
            done = new("done", this);
            cfg_en = new("cfg_en", this);
            cfg_burst = new("cfg_burst", this);
            status_busy = new("status_busy", this);
            dma = new("dma", this);
        endfunction
        function void connect();
            dma.cmd.connect(cmd);
            dma.done.connect(done);
            dma.cfg_en.connect(cfg_en);
            dma.cfg_burst.connect(cfg_burst);
            dma.status_busy.connect(status_busy);
        endfunction
    endclass
""",
}

WRAPS = {"fifo": (FIFO, "fw_rv_fifo", "q_like"), "arb": (ARB, "ref_arb3", "arb3_like"),
         "dma": (DMA, "dma_like", "dma_engine")}


def run_wrap(tmp_path, which):
    src, module, abstract = WRAPS[which]
    out = tmp_path / f"{which}.svh"
    assert wrap.main([str(src), "--module", module, "--abstract", abstract,
                      "-o", str(out)]) == 0
    return out


def package(tmp_path, which):
    pkg = tmp_path / "w_pkg.sv"
    pkg.write_text(f'`include "fw_hdl_macros.svh"\n\npackage w_pkg;\n'
                   f"    import fw_hdl_pkg::*;\n    import fw_std_pkg::*;\n"
                   f'    `include "{which}.svh"\n\n{TOPS[which]}endpackage\n')
    return pkg


def simulate(tmp_path, pkg, srcs, inputs, seed=5):
    design = spl_to_rtl([str(pkg)], "w_top", [])
    paths = []
    for name, text in design.files.items():
        (tmp_path / name).write_text(text)
        paths.append(tmp_path / name)
    tb = tmp_path / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, inputs, seed))
    out = run_verilator(paths + list(srcs) + [tb], "xh_rtl_tb", tmp_path / "rtl",
                        with_lib=False)
    return out


@pytest.mark.verilator
def test_fifo_round_trip(tmp_path):
    run_wrap(tmp_path, "fifo")
    xs = [r.randrange(256) for r in [random.Random(1)] for _ in range(100)]
    out = simulate(tmp_path, package(tmp_path, "fifo"), [FIFO], {"in": xs})
    assert [int(l.split()[3], 16) for l in out if l.startswith("O out ")] == xs


@pytest.mark.verilator
def test_arbiter_round_trip(tmp_path):
    run_wrap(tmp_path, "arb")
    r = random.Random(2)
    ins = {n: [r.randrange(256) for _ in range(50)] for n in ("a", "b", "c")}
    out = simulate(tmp_path, package(tmp_path, "arb"), [ARB], ins, seed=7)
    per = {0: [], 1: [], 2: []}
    for v in (int(l.split()[3], 16) for l in out if l.startswith("O out ")):
        per[v >> 8].append(v & 0xff)
    assert per == {i: ins[n] for i, n in enumerate(("a", "b", "c"))}


#: What a person adds to the dma_like wrapper: its timing, from the datasheet.
DMA_FACTS = """\
        f.latency(cmd, done, .min(2), .max(9));
        f.ii(cmd, 2);
"""


@pytest.mark.verilator
def test_dma_round_trip_after_editing(tmp_path):
    svh = run_wrap(tmp_path, "dma")
    text = svh.read_text()
    marker = "        // TODO: what the datasheet or a measurement says, for example:\n"
    assert marker in text
    svh.write_text(text.replace(marker, DMA_FACTS))
    pkg = package(tmp_path, "dma")
    p = partition([str(pkg)], "w_top", [])
    dma = next(c for c in p.shell.children if c["name"] == "dma")
    assert [f["kind"] for f in dma["facts"]] == ["iface.latency", "iface.ii"]
    assert dma["extern"]["ties"] == {"scan_en": "1'd0"}
    assert dma["extern"]["opens"] == ["dbg_state"]
    xs = [r.randrange(1 << 16) for r in [random.Random(3)] for _ in range(40)]
    out = simulate(tmp_path, pkg, [DMA], {"cmd": xs, "cfg_en": [1], "cfg_burst": [2]})
    assert [int(l.split()[3], 16) for l in out if l.startswith("O done ")] == \
        [x & 0xff for x in xs]
    # Wrapping again does not touch the edited file.
    src, module, abstract = WRAPS["dma"]
    assert wrap.main([str(src), "--module", module, "--abstract", abstract,
                      "-o", str(svh)]) == 1
    assert "f.ii(cmd, 2);" in svh.read_text()
    assert "f.ii(cmd, 2);" not in (tmp_path / "dma.svh.new").read_text()


def finish_cosim(path, cls, params, rename):
    """The edit the skeleton asks for: the class, its parameters, its port names."""
    d = yaml.safe_load(path.read_text())
    assert d["class"] == WRAPS[path.name.split(".")[0]][2]
    d["class"], d["params"] = cls, params
    t = d["targets"][0]
    t["ports"] = {rename(k): v for k, v in t["ports"].items()}
    path.write_text(yaml.safe_dump(d, sort_keys=False))
    return cosim.load(path)


@pytest.mark.verilator
@pytest.mark.parametrize("which, cls, params, rename", [
    ("fifo", "fw_channel", {"W": 8, "DEPTH": 1}, {"in": "put_ex", "out": "get_ex"}.get),
    ("arb", "fw_arbiter", {"W": 8, "N": 3},
     lambda k: "out" if k == "gnt" else k.replace("req", "in")),
])
def test_cosim_skeleton(tmp_path, which, cls, params, rename):
    run_wrap(tmp_path, which)
    spec = finish_cosim(tmp_path / f"{which}.cosim.yaml", cls, params, rename)
    res = cosim.run(spec, tmp_path / "cosim", (1, 2), None, str(VERILATOR))
    assert res and all(v == [] for v in res.values()), res
