# aes: AES-128/256, as functions

From XLS's `xls/modules/aes/{constants,aes_common,aes,aes_ctr}.x` (`orig/`, unmodified).
`aes_ctr.x`, the counter-mode proc, is ported in [`../aes_ctr`](../aes_ctr).

## The tests

The six `#[test]`s of aes.x, transcribed in [`aes_unit_test.sv`](aes_unit_test.sv) (the
vectors copied mechanically): the key schedule at 128 and 256 bits, encrypt at both, and
decrypt-of-encrypt at both.

Upstream writes `Key:[u8:0x00, ..., u8:0x0f, ...]`: a DSLX `...` repeats the *last*
element, so the rest of the key is `0x0f`, not zero. The transcription keeps that.

## The port

| DSLX | SV ([`aes_pkg.sv`](aes_pkg.sv)) |
|---|---|
| `type Block = u8[4][4]` | `typedef bit [7:0] Block [4][4]` |
| `word as u8[4]`, `bytes as KeyWord` | `word_bytes`, `bytes_word`: element 0 the most significant byte |
| `constants::S_BOX` and the other tables | `localparam` tables, copied from constants.x by script |
| `match (a, b, c) { (true, _, _) => ..., (_, true, _) => ..., ... }` | `if (a) ... else if (b) ... else if (c) ... else ...` |
| `std::mod_pow2(x, y)` | `x & (y - 1)` |
| `Block:[[...], ...]` literals of `block[i][j]` | loops over `i`, `j` |

**Found here:** an argument named `block`, as AES's are, is a keyword in XLS IR. The
XLS back end now prints such names with a trailing `_`.

## Equivalence

All three functions are **inconclusive** within the solver budget. Their optimized
graphs match in size (494 and 494, 2,234 and 2,234, 4,247 and 4,248 nodes); the tests at
every level are the evidence.

**Memory.** Yosys needs about 14 GB per AES-sized module (XLS's AES output goes through
sv2v; xls-examples.md G-6). Run the AES examples with a few jobs at a time
(`dfm run -j 4 aes.all`).
