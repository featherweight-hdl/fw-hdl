# adler32: Adler-32 of one byte

From XLS's `xls/examples/adler32/adler32.x` (`orig/`, unmodified; pinned in `orig/UPSTREAM`).

## The test

```
#[test]
fn adler32_one_char_test() {
    assert_eq(u32:0x0010001, main(u8:0x00));  // dec 0
    ...
}
```

```systemverilog
`SVTEST(adler32_one_char_test)
    bit [31:0] got;
    api.main(8'h00, got); `FAIL_UNLESS_EQUAL(got, 32'h0010001)  // dec 0
    ...
`SVTEST_END
```

[`adler32_unit_test.sv`](adler32_unit_test.sv) runs unedited at `model`, `rtl`, `gates`,
`gates-ice40` and `gates-ecp5`; [`../RESULTS.md`](../RESULTS.md) has the numbers.

## The port

| DSLX | SV ([`adler32_pkg.sv`](adler32_pkg.sv)) |
|---|---|
| `let (a, b) = for (_, (a, b)): (u8, (u32, u32)) in u8:0..u8:1 {...}((a, b))` | `for (int i = 0; i < 1; i++)` with `a`, `b` as locals |
| `(a + (buf as u32)) % u32:65521` | `(a + 32'(buf_)) % 32'd65521` -- `%` by a constant needs no guard |

Deviation: DSLX's parameter `buf` is an SV keyword (a gate primitive), so it is `buf_`.

Proven equivalent to the DSLX; both optimize to 6 nodes (one byte never reaches the
modulus, so `opt_main` folds it away).
