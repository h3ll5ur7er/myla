---
id: MYLA-600
title: "The interpreter's StringBuilder holds each byte in a word: a 20 MB string takes 280 MB to build"
type: bug
status: review
priority: low
labels: [interpreter, memory, performance]
---
Found by [[MYLA-553]]'s lane while it made the standard library's long paddings go in bulk ([[MYLA-546]]). The interpreter's `StringBuilder` is `Value.VSB([int64])` ([[selfhost/interp.my]], [[Architecture/Interpreter]]): one `int64` for each byte, so what it builds takes eight times its size, and twice that while the list grows. Native code's builder is a byte buffer.

```myla
fun main() {
    var block = "0000000000000000"
    while block.len() < 4096 {
        block = block + block
    }
    var sb = StringBuilder()
    for i in 0..5000 {
        sb.append(block)
    }
    let s = sb.build()
    print(s.len())
}
// output:
// 20480000
```

`myla run`: 0.65 s and a peak of 280 MB; natively 0.12 s and 55 MB. `num.to_hex(255u64, 2^30)`, which the library now pads 4,096 zeros at a time, ran 17 s interpreted with a peak of 10.3 GB (natively 1.4 s, 2 GB); `tests/burn/test_generated_extremes.py` leaves that case out (`NEVER`) for its size on every runner.

- [x] A builder of packed bytes in the interpreter (a `[uint8]` that is packed, if [[MYLA-546]]'s "packed bytes" box gives it one, or the bytes as a string's), so that a builder takes its size, as natively
- [x] The program above under about 60 MB interpreted, and the interpreter's suites as fast as before

## What was built

The interpreter's builder is the host's own: `Value.VSB(StringBuilder)` ([[selfhost/interp.my]]), its bytes packed as natively. An append takes it out of its cell (`sb_of`, the cell emptied first, as a list's push does, MYLA-74), so it is the only reference and grows in place, then puts it back; `StringBuilder(n)` gives it the room for `n` bytes, as natively (the capacity was evaluated and dropped). `sb_bytes`, `empty_bytes` and `bytes_to_str` went; `bytes_repr`, the `py_repr` of a builder, reads the built string. [[Architecture/Interpreter]]'s table of values says so.

## Evidence

- **Failing first.** `test_selfhost_interp…test_a_builder_takes_its_size` (the program above, its peak against an empty program's plus 60 MB) against the base (aef0b21's `interp.my`): fails, a peak of 279.6 MB against 10.9 MB; passes now.
- **The program above** (`myla run`, peak resident memory, wall time), before → after: 279.6 MB → 62.8 MB, 0.38 s → 0.055 s; an empty program takes 10.9 MB, so the builder and the string take 52 MB, as natively (55.0 MB, 0.04 s, with no interpreter around them).
- **`num.to_hex(255u64, 100000000)`** (a tenth of the review's 2^30, which needs 3 GB natively too): 1.60 s and 1,051 MB → 0.29 s and 215 MB interpreted (natively 0.17 s and 207 MB). `test_generated_extremes.py` keeps leaving out the 2^30 case (`NEVER`): natively it is `out of memory` under the gigabyte a run may take.
- The suites, and that they are as fast as before: [[MYLA-605]]'s evidence (the three tasks measured together).
