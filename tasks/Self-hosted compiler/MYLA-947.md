---
id: MYLA-947
title: "Small `var self` methods of a struct in another module cost 1.7 to 2.6 times the same loop by hand"
type: improvement
status: todo
priority: medium
labels: [performance, native, stdlib, images]
---
Found by [[MYLA-931]] (`benchmarks/bytes_std.my`, native x86-64, 100 MiB, best of 5): `ByteReader.u32_be` 136 ms against 78 ms by hand, 13-bit codes from `MsbBitReader.bits` 405 ms against 153 ms, `LsbBitReader` 483 against 216 ms, `MsbBitWriter.put_bits` 508 against 298 ms. A reader declared in the caller's module, one without the `Option`, and the fields used directly all took 170 to 270 ms against 90 ms by hand, so the cost is the struct's state loaded and stored through `self` on every call and the call itself, not inlined across modules.

Every codec of [[Project/Standard-library-roadmap/Images-vision-and-fonts]] reads its input through these readers, so this bounds their speed.

- [ ] A profile of the generated code for `bits(13)` in a loop: what each call loads, stores and calls
- [ ] Inlining small leaf methods (across modules) and keeping a `var self` struct's fields in registers through the inlined body, or the measured reason it can't be done
- [ ] `benchmarks/bytes_std.my` measured again: within 20 % of the loops by hand
