# Probe: transactor role base classes

Can a transactor take its role, protocol and pin member from a base class
parameterized on its bundle type, in Verilator 5.055 against rt-sv and
std? Yes (2026-11-18).

```systemverilog
virtual class fw_xtor_initiator #(type B) extends fw_component;  // fw_bundle  #(B) pins
virtual class fw_xtor_target    #(type B) extends fw_component;  // fw_mirror  #(B) pins
virtual class fw_xtor_monitor   #(type B) extends fw_component;  // fw_monitor #(B) pins
//   static role();  static protocol() = B::__fw_bundle_protocol();  build() creates pins
`xb_xtor_utils(C)   // no PROTO argument: role() and protocol() come from the base
```

Run: `direnv exec . sh docs/design/probes/xtor-base/run.sh` from the
workspace root. The output should match `expected.txt`.

What it shows:
- `role()` is static. `q_tgt_unused` is never created and still reports
  `target`. rt-sv's instance-scanning `xtor_role` would fall back to
  initiator.
- `protocol()` comes from `B`:
  - `q_proto` for a plain transactor over a bundle of channels;
  - distinct `fw_rv_proto#(bit[7:0])` and `#(bit[15:0])` for two
    specializations of a parameterized transactor, the first being the
    same handle as std's.
- Registration through `add_conv` with the base's `role()` in a static
  initializer works, with no init-order problem.
- `pins` is created by the base with the right mixin (bundle, mirror,
  monitor). A subclass `build()` calls `super.build()`. Back-to-back and
  monitor connects work.
- `$typename(this_t)` inside a parameterized class keeps its parameters,
  so rt-sv's `conv_by_type` keys are distinct per specialization.

The 6 elaboration errors in `expected.txt` come from the probe's design,
not the base classes. The probe transactors have no API endpoints, so
`FW-E-PROTO-XTOR` fires (the monitor is correctly exempt), and the rv
transactors' pins are left unconnected.
