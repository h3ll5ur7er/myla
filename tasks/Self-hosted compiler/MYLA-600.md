---
id: MYLA-600
title: "The interpreter's StringBuilder holds each byte in a word: a 20 MB string takes 280 MB to build"
type: bug
status: in-progress
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

- [ ] A builder of packed bytes in the interpreter (a `[uint8]` that is packed, if [[MYLA-546]]'s "packed bytes" box gives it one, or the bytes as a string's), so that a builder takes its size, as natively
- [ ] The program above under about 60 MB interpreted, and the interpreter's suites as fast as before
