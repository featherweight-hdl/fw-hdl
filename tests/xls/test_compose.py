"""X2 (xls-phase2.md): the T1 composition rle_enc8 -> pkt_framer -> crc32_stream.

ST-2: the structure of chain_top as zuspec IR.
ST-3: chain_top on Verilator (the SPL view) against a Python reference model.
"""
import random
import re
import zlib
from pathlib import Path

import pytest

import zuspec.ir.core as ir
from fw.hdl.xls_flow import sv_to_structure
from xls_harness import proc_testbench, run_verilator

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
FILES = [str(CORPUS / "crc32_pkg.sv"), str(CORPUS / "rle_pkg.sv"), str(CORPUS / "rle8_pkg.sv"),
         str(HERE / "compose" / "chain_pkg.sv")]
PKGS = ["rle8_pkg", "crc32_pkg", "chain_pkg"]


def reference(xs):
    """rle_enc8, then two {last, byte} beats per packet with every fourth packet
    ending a frame, then the CRC-32 of each frame."""
    pkts, valid, last, cnt = [], False, 0, 0
    for x in xs:
        if valid and (x != last or cnt == 0xFF):
            pkts.append((last, cnt))
        cnt = cnt + 1 if (valid and x == last and cnt != 0xFF) else 1
        last, valid = x, True
    crcs = []
    for i in range(0, len(pkts) - len(pkts) % 4, 4):
        crcs.append(zlib.crc32(bytes(b for p in pkts[i:i + 4] for b in p)))
    return crcs


def stimulus(seed: int, n: int):
    rng = random.Random(seed)
    xs = []
    while len(xs) < n:
        xs += [rng.choice([0x41, 0x42, 0x43, rng.getrandbits(8)])] * rng.choice([1, 1, 2, 3, 7])
    return xs[:n]


def _name(comp, e):
    if isinstance(e, ir.ExprAttribute):
        return _name(comp, e.value) + "." + e.attr
    return comp.fields[e.index].name


def test_st2_chain_top_structure():
    st = sv_to_structure(FILES, "chain_top")
    c = st.component
    roles = {f.name: f.pragmas.get("fw_role", "port") for f in c.fields}
    assert roles == {"in": "port", "out": "port", "rle": "child", "fr": "child",
                     "crc": "child", "c0": "channel", "c1": "channel"}
    chans = {f.name: (f.datatype.depth, f.datatype.element_type.bits)
             for f in c.fields if isinstance(f.datatype, ir.DataTypeChannel)}
    assert chans == {"c0": (0, 16), "c1": (2, 9)}
    assert [(_name(c, b.lhs), _name(c, b.rhs)) for b in c.bind_map] == [
        ("rle.in", "in"), ("rle.out", "c0.put_ex"), ("fr.in", "c0.get_ex"),
        ("fr.out", "c1.put_ex"), ("crc.in", "c1.get_ex"), ("crc.out", "out")]
    assert {n: ch.spelling for n, ch in st.children.items()} == \
        {"rle": "rle_enc8_t", "fr": "pkt_framer", "crc": "crc32_stream"}


@pytest.mark.verilator
def test_st3_chain_top_spl_view(workdir):
    xs = stimulus(1, 400)
    want = reference(xs)
    assert len(want) >= 10
    comp = sv_to_structure(FILES, "chain_top").component
    workdir.mkdir(parents=True, exist_ok=True)
    tb = workdir / "xh_proc_tb.sv"
    tb.write_text(proc_testbench(PKGS, "chain_top", comp, {"in": xs}))
    out = run_verilator(FILES + [tb], "xh_proc_tb", workdir)
    got = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    assert got == want


# ---------------------------------------------------------------------------
# ST-2 rejections: each points at the line marked `// HERE`.
# ---------------------------------------------------------------------------
STRUCT = """package sneg_pkg;
    import fw_hdl_pkg::*;
    import fw_std_pkg::*;
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
@@MEMBERS@@
        function new(string name, fw_component parent);
            super.new(name, parent);
        endfunction
        function void build();
            in = new("in", this);
            out = new("out", this);
            a = new("a", this);
            b = new("b", this);
@@BUILD@@
        endfunction
        function void connect();
            a.in.connect(in);
            b.out.connect(out);
@@CONNECT@@
        endfunction
    endclass
endpackage
"""

GOOD_BUILD = '            ch = new("ch", this);'
GOOD_CONNECT = "            a.out.connect(ch.put_ex);\n            b.in.connect(ch.get_ex);"

STRUCT_CASES = [
    ("good", "", GOOD_BUILD, GOOD_CONNECT, None),
    ("child_to_child",
     "", GOOD_BUILD,
     # type-legal (get port to get port), so slang accepts it; we don't
     "            a.out.connect(ch.put_ex);\n            b.in.connect(a.in);  // HERE",
     r"provider must be a channel end"),
    ("unconnected_port", "", GOOD_BUILD, "            b.in.connect(ch.get_ex);",
     r"port a\.out is not connected"),
    ("connected_twice", "", GOOD_BUILD,
     GOOD_CONNECT + "\n            a.out.connect(ch.put_ex);  // HERE",
     r"a\.out is connected twice"),
    ("wrong_instance_name", "", '            ch = new("fifo", this);  // HERE', GOOD_CONNECT,
     r"must be constructed as new\(\"ch\", this\)"),
    ("not_constructed", "", "", GOOD_CONNECT, r"does not construct \['ch'\]"),
    ("loop_in_build", "", GOOD_BUILD + "\n            for (int i = 0; i < 1; i++) a = new(\"a\", this);  // HERE",
     GOOD_CONNECT, r"may only construct its fields"),
    ("data_property", "        bit [7:0] count;  // HERE", GOOD_BUILD, GOOD_CONNECT,
     r"holds only ports, child components and channels"),
]


@pytest.mark.parametrize("case", STRUCT_CASES, ids=[c[0] for c in STRUCT_CASES])
def test_st2_structure_rules(tmp_path, case):
    from fw.hdl.errors import FwHdlError
    _, members, build, connect, msg = case
    text = STRUCT.replace("@@MEMBERS@@", members).replace("@@BUILD@@", build) \
        .replace("@@CONNECT@@", connect)
    path = tmp_path / "sneg_pkg.sv"
    path.write_text(text)
    if msg is None:
        sv_to_structure([str(path)], "top")
        return
    with pytest.raises(FwHdlError) as ex:
        sv_to_structure([str(path)], "top")
    assert re.search(msg, str(ex.value)), str(ex.value)
    lines = [i + 1 for i, l in enumerate(text.splitlines()) if "// HERE" in l]
    if lines:
        m = re.search(r"sneg_pkg\.sv:(\d+):\d+", str(ex.value))
        assert m and int(m.group(1)) == lines[0], str(ex.value)


# ---------------------------------------------------------------------------
# T1 RTL view: partition -> XLS per class -> structural top, on Verilator.
# ---------------------------------------------------------------------------
from zuspec.be.xls.testing.xlstools import codegen_main, opt_main  # noqa: E402

needs_xls = pytest.mark.skipif(codegen_main() is None or opt_main() is None,
                               reason="needs opt_main and codegen_main")
XLS_CLASSES = ["rle_enc8_t", "pkt_framer", "crc32_stream"]


@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("stages,seed", [(1, 1), (2, 2)])
def test_t1_chain_top_rtl_view(workdir, stages, seed):
    from fw.hdl.spl_flow import spl_to_rtl
    from xls_harness import REPO, rtl_testbench
    xs = stimulus(seed, 400)
    want = reference(xs)
    design = spl_to_rtl(FILES, "chain_top", XLS_CLASSES, stages=stages)
    workdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in design.files.items():
        (workdir / name).write_text(text)
        paths.append(workdir / name)
    tb = workdir / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(design.signature, {"in": xs}, seed))
    out = run_verilator(paths + [REPO / "src" / "rtl" / "fw_rv_fifo.sv", tb], "xh_rtl_tb",
                        workdir / "rtl", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    got = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    assert got == want


def test_part_rejects_unassigned_and_unknown_classes():
    from fw.hdl.errors import FwHdlError
    from fw.hdl.spl_flow import partition
    from fw.hdl.xls_flow import XlsFlowError
    with pytest.raises(FwHdlError, match=r"child 'fr' \(pkt_framer\) is not assigned") as ex:
        partition(FILES, "chain_top", ["rle_enc8_t", "crc32_stream"])
    line = next(i + 1 for i, l in enumerate(Path(FILES[3]).read_text().splitlines())
                if "pkt_framer                     fr;" in l)
    assert re.search(rf"chain_pkg\.sv:{line}:", str(ex.value)), str(ex.value)
    with pytest.raises(XlsFlowError, match=r"\['nosuch'\] assigned to XLS but not instantiated"):
        partition(FILES, "chain_top", XLS_CLASSES + ["nosuch"])


# ---------------------------------------------------------------------------
# The same T1 through dv-flow: spl.Partition -> synth.xls.Codegen ->
# zuspec.xls.Signature -> spl.Integrate (tests/xls/compose/flow.yaml). The
# simulation uses only the files the last task outputs.
# ---------------------------------------------------------------------------
@needs_xls
@pytest.mark.verilator
@pytest.mark.parametrize("task", ["chain-rtl", "chain-rtl-recipe"])
def test_t1_through_dv_flow(workdir, task):
    import json
    import os
    import shutil
    import subprocess
    from xls_harness import REPO, rtl_testbench
    dfm = REPO / "packages" / "python" / "bin" / "dfm"
    root = workdir / "proj"
    shutil.copytree(REPO, root, symlinks=True, ignore=shutil.ignore_patterns(
        "packages", "rundir", ".git", "*.old*", "__pycache__", "examples", "reference", "docs"))
    os.symlink(REPO / "packages", root / "packages")
    env = dict(os.environ)
    tools = os.path.dirname(codegen_main())
    env["PATH"] = tools + os.pathsep + env.get("PATH", "")
    r = subprocess.run([str(dfm), "run", "-f", f"compose.{task}"], cwd=root, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    data = json.loads((root / "rundir" / f"fw-hdl.compose.{task}" /
                       f"fw-hdl.compose.{task}.exec_data.json").read_text())
    outs = data["output"]["output"]
    srcs = [Path(fs["basedir"]) / f for fs in outs
            if fs["filetype"] == "systemVerilogSource" for f in fs["files"]]
    sig_file = [Path(fs["basedir"]) / f for fs in outs
                if fs["filetype"] == "blockSignature" for f in fs["files"]]
    assert [p.name for p in srcs] == ["fw_rv_fifo.sv", "rle_enc8_t.sv", "pkt_framer.sv",
                                      "crc32_stream.sv", "chain_top.sv"]
    assert {fs["filetype"] for fs in outs} == {"systemVerilogSource", "blockSignature"}
    sig = ir.load_signature(str(sig_file[0]))
    xs = stimulus(3, 400)
    tb = workdir / "xh_rtl_tb.sv"
    tb.write_text(rtl_testbench(sig, {"in": xs}, 3))
    out = run_verilator(srcs + [tb], "xh_rtl_tb", workdir / "sim", with_lib=False,
                        extra=["--assert", "+define+ASSERT_ON"])
    got = [int(l.split()[3], 16) for l in out if l.startswith("O out ")]
    assert got == reference(xs)
