"""Unit tests for fw.hdl.fe.parser — pyslang wrapper + library wiring."""
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.parser import Parser
from fw.hdl.fe import astdump


def test_parse_blinky_clean(blinky_files):
    reporter = ErrorReporter()
    parser = Parser(FlowConfig(), reporter)
    ok = parser.parse(blinky_files)
    assert ok, reporter.report()
    assert not reporter.has_errors()


def test_blinky_class_found(blinky_files):
    parser = Parser(FlowConfig(), ErrorReporter())
    assert parser.parse(blinky_files)
    names = [c.name for c in astdump.collect_user_classes(parser.get_root())]
    assert "blinky" in names


def test_library_classes_filtered(blinky_files):
    parser = Parser(FlowConfig(), ErrorReporter())
    assert parser.parse(blinky_files)
    names = [c.name for c in astdump.collect_user_classes(parser.get_root())]
    # fw_* / zsp_* library classes must not appear in the design listing.
    assert not any(n.startswith(("fw_", "zsp_")) for n in names)


def test_parse_text_simple_class():
    reporter = ErrorReporter()
    parser = Parser(FlowConfig(), reporter)
    ok = parser.parse_text("package p; class c; int x; endclass endpackage", "t.sv")
    assert ok, reporter.report()


def test_syntax_error_reported():
    reporter = ErrorReporter()
    parser = Parser(FlowConfig(), reporter)
    ok = parser.parse_text("class c; int x endclass", "bad.sv")  # missing ';'
    assert not ok
    assert reporter.has_errors()


def test_define_controls_preprocessing():
    # FOO gates a syntactically-required member; without the define the class is
    # empty-but-valid, with it the member appears. We assert the define path
    # parses cleanly and that predefine rendering is correct.
    cfg = FlowConfig(defines={"WIDTH": "8", "ENABLE": ""})
    assert set(cfg.predefine_strings()) == {"WIDTH=8", "ENABLE"}

    text = "package p;\n`ifdef ENABLE\nclass c; int x; endclass\n`endif\nendpackage"
    parser = Parser(cfg, ErrorReporter())
    assert parser.parse_text(text, "t.sv")
    names = [c.name for c in astdump.collect_user_classes(parser.get_root())]
    assert "c" in names
