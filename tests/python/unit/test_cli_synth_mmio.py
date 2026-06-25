"""F-A5: the ``fw-hdl synth-mmio`` orchestration produces the design modules."""
from fw.hdl.cli import main


def test_synth_mmio_writes_modules(mmio_dir, tmp_path):
    rc = main(["synth-mmio",
               str(mmio_dir / "mmio_pkg.sv"),
               str(mmio_dir / "mmio_tb.sv"),
               "--top-module", "mmio_top",
               "-o", str(tmp_path) + "/"])
    assert rc == 0
    produced = {p.name for p in tmp_path.glob("*.sv")}
    assert produced == {"mmio_regs_regblock.sv", "mmio_fsm.sv", "mmio_top.sv"}

    top = (tmp_path / "mmio_top.sv").read_text()
    assert "mmio_regs_regblock u_regs (" in top
    assert "mmio_fsm u_mmio_fsm (" in top
    # the FSM module is the Mealy comb the lowering produced
    assert "always @(*)" in (tmp_path / "mmio_fsm.sv").read_text()


def test_synth_mmio_no_component_errors(blinky_files, capsys):
    """A design with no MMIO component reports an error, not a crash."""
    rc = main(["synth-mmio", *blinky_files])
    assert rc == 1
    assert "no MMIO component" in capsys.readouterr().err
