"""§6.2 design corpus: each design's reference vectors on Verilator (the
normative SV) and in the interpreter on the emitted XLS IR."""
import binascii
import random
from pathlib import Path

import pytest

from xls_harness import FnCheck, check_functions, check_proc

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"


def _stream(msgs):
    out = []
    for m in msgs:
        out += [b | (0x100 if k == len(m) - 1 else 0) for k, b in enumerate(m)]
    return out


@pytest.mark.verilator
def test_c1_crc32_function(workdir):
    pkg = str(CORPUS / "crc32_pkg.sv")
    words = [0x34333231, 0x0, 0xFFFFFFFF, 0xDEADBEEF] + \
        [random.Random(1).getrandbits(32) for _ in range(60)]
    r = check_functions([pkg], "crc32_pkg", [
        FnCheck("crc32_4", [(w,) for w in words]),
        FnCheck("crc32_step", [(c, b) for c in (0, 0xFFFFFFFF, 0x12345678) for b in range(256)]),
    ], workdir)
    assert r["crc32_4"] == [binascii.crc32(w.to_bytes(4, "little")) for w in words]
    assert r["crc32_4"][0] == binascii.crc32(b"1234")


@pytest.mark.verilator
def test_c1_crc32_stream(workdir):
    msgs = [b"123456789", b"hello, world", b"\x00", bytes(range(64))]
    r = check_proc([str(CORPUS / "crc32_pkg.sv")], "crc32_pkg", "crc32_stream",
                   {"in": _stream(msgs)}, workdir)
    assert r.outputs["out"] == [binascii.crc32(m) for m in msgs]
    assert r.outputs["out"][0] == 0xCBF43926


def rle_model(xs, w):
    """The reference run-length encoder: (symbol, count) per run, count <= 255,
    emitted when the run ends (the final run is still open)."""
    out, last, cnt, valid = [], 0, 0, False
    for x in xs:
        if valid and (x != last or cnt == 0xFF):
            out.append((last << 8) | cnt)
        cnt = cnt + 1 if (valid and x == last and cnt != 0xFF) else 1
        last, valid = x, True
    return out


@pytest.mark.verilator
@pytest.mark.parametrize("top,w", [("rle_enc8_t", 8), ("rle_enc4_t", 4)])
def test_c2_rle(workdir, top, w):
    # one specialization per build: see the note in corpus/rle8_pkg.sv
    files = [str(CORPUS / "rle_pkg.sv"), str(CORPUS / f"rle{w}_pkg.sv")]
    rng = random.Random(w)
    xs = []
    for _ in range(40):
        xs += [rng.getrandbits(w)] * rng.choice([1, 1, 2, 3, 7])
    xs += [5] * 300                          # a run longer than 255 splits
    xs += [6]
    r = check_proc(files, ["rle_pkg", f"rle{w}_pkg"], top, {"in": xs}, workdir)
    assert r.outputs["out"] == rle_model(xs, w)


# ---------------------------------------------------------------------------
# C3 / C4: AES-128
# ---------------------------------------------------------------------------

AES = str(CORPUS / "aes_pkg.sv")
FIPS197 = [
    # Appendix B
    (0x2b7e151628aed2a6abf7158809cf4f3c, 0x3243f6a8885a308d313198a2e0370734,
     0x3925841d02dc09fbdc118597196a0b32),
    # Appendix C.1
    (0x000102030405060708090a0b0c0d0e0f, 0x00112233445566778899aabbccddeeff,
     0x69c4e0d86a7b0430d8cdb78070b4c55a),
]


@pytest.mark.verilator
def test_c3_aes128_functions(workdir):
    rng = random.Random(3)
    vecs = [(k, p) for k, p, _ in FIPS197] + \
        [(rng.getrandbits(128), rng.getrandbits(128)) for _ in range(16)]
    r = check_functions([AES], "aes_pkg", [
        FnCheck("aes128_encrypt", vecs),
        FnCheck("mix_column", [(rng.getrandbits(32),) for _ in range(64)] + [(0xdb135345,)]),
        FnCheck("shift_rows", [(rng.getrandbits(128),) for _ in range(8)]),
        FnCheck("sub_bytes", [(rng.getrandbits(128),) for _ in range(8)]),
    ], workdir)
    assert r["aes128_encrypt"][:2] == [ct for _, _, ct in FIPS197]
    assert r["mix_column"][-1] == 0x8e4da1bc          # FIPS-197 §5.1.3 example


SP800_38A_F51_KEY = 0x2b7e151628aed2a6abf7158809cf4f3c
SP800_38A_F51_CTR = 0xf0f1f2f3f4f5f6f7f8f9fafbfcfdfeff
SP800_38A_F51_PT = [0x6bc1bee22e409f96e93d7e117393172a, 0xae2d8a571e03ac9c9eb76fac45af8e51,
                    0x30c81c46a35ce411e5fbc1191a0a52ef, 0xf69f2445df4f9b17ad2b417be66c3710]
SP800_38A_F51_CT = [0x874d6191b620e3261bef6864990db6ce, 0x9806f66b7970fdff8617187bb9fffdff,
                    0x5ae4df3edbd5d35e5b4f09020db03eab, 0x1e031dda2fbe03d1792170a0f3009cee]


@pytest.mark.verilator
def test_c4_aes128_ctr(workdir):
    def cmd(key, ctr, n):
        return (key << 136) | (ctr << 8) | n
    rng = random.Random(4)
    k2, c2 = rng.getrandbits(128), (1 << 128) - 2      # the counter wraps
    pts2 = [rng.getrandbits(128) for _ in range(3)]
    r = check_proc([AES], "aes_pkg", "aes_ctr", {
        "cmd": [cmd(SP800_38A_F51_KEY, SP800_38A_F51_CTR, 4), cmd(k2, c2, 3)],
        "din": SP800_38A_F51_PT + pts2,
    }, workdir)
    assert r.outputs["dout"][:4] == SP800_38A_F51_CT
    assert len(r.outputs["dout"]) == 7
