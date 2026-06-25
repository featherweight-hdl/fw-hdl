"""P3: rtl2v — emit Verilog from RTL IR via be-sv."""
from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl import flow


def _sv(blinky_files):
    reporter = ErrorReporter()
    cfg = FlowConfig(top="blinky", top_module="blinky_top")
    result = flow.synth(blinky_files, cfg, reporter)
    assert result is not None, reporter.report()
    return result.sv


def test_module_header_and_ports(blinky_files):
    sv = _sv(blinky_files)
    assert "module blinky(" in sv
    assert "input logic clock" in sv
    assert "input logic reset" in sv
    assert "output logic led" in sv


def test_internal_regs_not_ports(blinky_files):
    sv = _sv(blinky_files)
    assert "logic [7:0] count" in sv      # internal reg, sized (down-counter, +1 borrow bit)
    assert "logic state" in sv
    assert "input logic count" not in sv   # the spike trap
    assert "input logic state" not in sv


def test_fsm_body(blinky_files):
    sv = _sv(blinky_files)
    assert "always @(posedge clock)" in sv
    assert "if (reset)" in sv               # fw-hdl std: active-high reset
    assert "state == 0" in sv               # ExprCompare, not '?'
    assert "count <= 99" in sv              # down-counter preload (tick reload)
    assert "count[7]" in sv                 # terminal = underflow MSB (no wide comparator)
    assert "led <= v" in sv                 # put beat registers led
    assert "v <= ~v" in sv                  # toggle
    assert "count <= (count - 1)" in sv     # decrement
    assert "count == 99" not in sv          # the wide equality comparator is gone


def test_report_lists_registers(blinky_files):
    reporter = ErrorReporter()
    cfg = FlowConfig(top="blinky", top_module="blinky_top")
    result = flow.synth(blinky_files, cfg, reporter)
    assert "module blinky" in result.report
    assert "clocked processes: 1" in result.report
