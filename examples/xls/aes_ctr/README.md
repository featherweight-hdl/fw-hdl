# aes_ctr: AES in counter mode, as a proc

From XLS's `xls/modules/aes/aes_ctr.x` (in [`../aes/orig`](../aes/orig), unmodified), on
the AES functions of [`../aes`](../aes).

## The test

`aes_ctr_test_128`, transcribed in [`aes_ctr_unit_test.sv`](aes_ctr_unit_test.sv): two
commands of encryption and one of decryption, sent to the proc through the generated
component API (`command_in_put`, `ptxt_in_put`, `ctxt_out_get`).

## The port

| DSLX | SV ([`aes_ctr_pkg.sv`](aes_ctr_pkg.sv)) |
|---|---|
| `struct Command { msg_bytes, key: Key, ... }` | a packed struct; the key a packed `bit [31:0][7:0]` |
| `chan<Block>` | `fw_port #(... PBlock)`: a block on a channel as a packed `bit [3:0][3:0][7:0]` |
| `enum Step : bool` | `typedef enum bit {IDLE, PROCESSING}` |
| `recv_if(join(), command_in, step == Step::IDLE, zero!<Command>())` | `if (step == IDLE) command_in.t.get(cmd);` |
| `cmd.iv ++ ctr` | `{cmd.iv, ctr_}` |

Deviations, both because a port's payload must be packed:

* The key in `Command` and the blocks on the channels are packed arrays. The static
  subset takes descending packed ranges only, so DSLX element `k` of `n` is index
  `n-1-k`: `key[k]` is `cmd.key[31 - k]`. The bit layout is DSLX's (element 0 most
  significant).
* `pack_block` / `unpack_block` convert between the channel's packed block and the
  functions' `aes_pkg::Block`.

xls-examples.md expected this proc to be *rejected*, because it would do several sends
and receives on one channel per activation (P10). That was read from google/xls `main`.
At the pinned tag, `next` does one operation per channel, so the faithful port is
accepted.
