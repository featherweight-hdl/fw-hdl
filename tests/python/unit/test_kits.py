"""Phase 1 K5, R6, T1 prep: fw-hdl's kit descriptors (src/std/**/*_kit.yaml)."""
import pytest
import yaml

from fw.hdl.fe.bind import protocols
from fw.hdl.kits import STD_KIT_PATHS, check_kits, registry, std_sv_files, sv_ports
from zuspec.synth.kits import KitRegistry, schema


def test_std_kits_load_and_validate():
    jsonschema = pytest.importorskip("jsonschema")
    reg = registry()
    assert sorted(reg.kits) == ["fw_put", "fw_rv"]
    for k in reg.kits.values():
        jsonschema.validate(yaml.safe_load(open(k.path)), schema("zuspec.kit"))


def test_std_kits_match_their_sv():
    """The stale-map check over the real transactor modules."""
    assert check_kits(registry(), std_sv_files()) == []


def test_stale_check_catches_a_renamed_sv_port(tmp_path):
    src = (STD_KIT_PATHS[0] + "/rv/fw_rv_initiator_xtor.sv")
    bad = tmp_path / "fw_rv_initiator_xtor.sv"
    bad.write_text(open(src).read().replace("output bit    valid", "output bit    vld"))
    files = [f for f in std_sv_files() if not f.endswith("/fw_rv_initiator_xtor.sv")] + [str(bad)]
    errs = check_kits(registry(), files)
    assert "fw_rv: fw_rv_initiator_xtor has no port 'valid'" in " ".join(errs)


def test_sv_ports_reads_directions():
    p = sv_ports([STD_KIT_PATHS[0] + "/rv/fw_rv_target_xtor.sv"])["fw_rv_target_xtor"]
    assert p == {"clock": "in", "reset": "in", "valid": "in", "ready": "out", "data": "in"}


def test_by_bridge_matches_the_std_transactor_table():
    for name, spec in protocols.STD_TRANSACTORS.items():
        got = registry().by_bridge(name)
        assert (got.protocol, got.method, got.data_port, got.pin_dir, got.registered) == \
            (spec.protocol, spec.method, spec.data_port, spec.pin_dir, spec.registered)


def test_default_resolution_for_std_apis():
    reg = registry()
    led = reg.resolve("fw_put_if", "port", ["led_t"], endpoint="led")
    assert (led.kit, led.bridge, led.module) == ("fw_put", "fw_put_xtor_bridge #(led_t)", "fw_put_xtor_if")
    inp = reg.resolve("fw_get_if", "port", ["pkt_t"], endpoint="pkt_in")
    assert (inp.kit, inp.source, inp.module) == ("fw_rv", "adapter", "fw_rv_target_xtor")
    assert inp.pins == {"data": "pkt_in", "valid": "pkt_in_valid", "ready": "pkt_in_ready"}


def test_project_kit_directory_adds_kits(tmp_path):
    (tmp_path / "fw_put2_kit.yaml").write_text(yaml.safe_dump({
        "format": "zuspec.kit", "version": 1, "kit": "fw_put2",
        "transactors": [{"api": "fw_put2_if", "endpoint": "port", "module": "fw_put2_xtor_if",
                         "bridge": "fw_put2_bridge #($T)", "ports": {"data": "q"},
                         "directions": {"data": "out"}, "method": "put", "registered": True}]}))
    reg = registry([str(tmp_path)])
    assert isinstance(reg, KitRegistry) and "fw_put2" in reg.kits
    assert reg.by_bridge("fw_put2_bridge").data_port == "q"
