"""fw.hdl.api for components (procs): the generated API and its bindings."""
from zuspec.ir.core import BlockSignature, ChannelSignature, DataTypeInt

from fw.hdl import comp_api


def _api():
    enc = comp_api.CompApi("Enc32", "rle_pkg::Enc32", "Enc32", [
        comp_api.CompPort("input_r", "put", "Enc32::InData", 33),
        comp_api.CompPort("output_s", "get", "Enc32::OutData", 35)])
    return comp_api.CompApiSet("rle_pkg_api", [enc])


def test_api_package_imports_the_component_package_and_names_getters_get_():
    sv = comp_api.api_pkg_sv(_api())
    assert "    import rle_pkg::*;" in sv
    assert "pure virtual task input_r_put(input Enc32::InData v);" in sv
    assert "pure virtual task output_s_get(output Enc32::OutData v);" in sv
    # A function named Enc32 would hide the imported type Enc32.
    assert "function automatic Enc32_api get_Enc32();" in sv
    assert "function automatic Enc32_api Enc32();" not in sv


def test_model_harness_runs_the_component_on_queues():
    sv = comp_api.model_harness_sv(_api())
    assert "class Enc32_input_r_src implements fw_get_if #(Enc32::InData);" in sv
    assert "class Enc32_output_s_snk implements fw_put_if #(Enc32::OutData);" in sv
    assert "rle_pkg::Enc32 Enc32_dut;" in sv
    assert "Enc32_dut.input_r.connect(Enc32_input_r_e);" in sv


def test_xls_binding_drives_and_collects_channels():
    sig = BlockSignature(name="Enc32", clock="clk", reset="rst", channels=[
        ChannelSignature(name="input_r", direction="in", payload=DataTypeInt(bits=33),
                         ports={"data": "input_r", "valid": "input_r_vld", "ready": "input_r_rdy"}),
        ChannelSignature(name="output_s", direction="out", payload=DataTypeInt(bits=35),
                         ports={"data": "output_s", "valid": "output_s_vld",
                                "ready": "output_s_rdy"})])
    sv = comp_api.xls_binding_sv(_api(), {"Enc32": sig})
    assert "if (input_r_vld && input_r_rdy) void'(q_input_r.pop_front());" in sv
    assert "if (output_s_vld && output_s_rdy) q_output_s.push_back(output_s);" in sv
    assert ".input_r_vld(Enc32_if.input_r_vld)" in sv
    # declarations before statements in the binding's initial block
    init = sv[sv.index("    initial begin\n        automatic"):]
    assert init.index("automatic") < init.index(".vif =")
    assert "package rle_pkg_api_xls_pkg;\n    import rle_pkg::*;" in sv
