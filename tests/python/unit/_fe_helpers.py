"""Helpers for the front-end mapper tests.

Maps a *self-contained* SystemVerilog snippet (no fw-hdl library needed) to an
SPL ``DataTypeComponent`` via the real mapper pipeline, so the type/expr/stmt/
class mappers can be unit-tested without the library or a simulator.
"""
from __future__ import annotations

import zuspec.ir.core as ir

from fw.hdl.config import FlowConfig
from fw.hdl.errors import ErrorReporter
from fw.hdl.fe.astdump import collect_user_classes
from fw.hdl.fe.class_mapper import ClassMapper
from fw.hdl.fe.parser import Parser


def parse_text(text: str):
    reporter = ErrorReporter()
    parser = Parser(FlowConfig(), reporter)
    assert parser.parse_text(text, "t.sv"), reporter.report()
    return parser, reporter


def get_class(text: str, name: str):
    parser, _ = parse_text(text)
    for c in collect_user_classes(parser.get_root()):
        if c.name == name:
            return c
    raise AssertionError(f"class {name!r} not found")


def spl_component(text: str, name: str) -> ir.DataTypeComponent:
    parser, reporter = parse_text(text)
    cls = next(c for c in collect_user_classes(parser.get_root()) if c.name == name)
    comp = ClassMapper(FlowConfig(), reporter).map_component(cls)
    assert not reporter.has_errors(), reporter.report()
    return comp


def run_body(comp: ir.DataTypeComponent):
    return comp.proc_processes[0].body
