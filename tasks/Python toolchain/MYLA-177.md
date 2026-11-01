---
id: MYLA-177
title: "`as char` is unchecked: surrogates and values above 10FFFF"
type: bug
status: review
priority: medium
labels: [checker, chars, parity]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `char` is documented as a Unicode scalar, but `0xD800 as char` and `0x110000 as char` are accepted: printing the first crashes the interpreter with `UnicodeDecodeError`, native code prints three garbage bytes; the second prints 1114112 as an integer. The checker, the interpreter and the code generator each say the cast is unchecked. Needs a decision: trap at run time (like an out-of-range index), saturate (D59's answer for floats), or forbid the cast from integers wider than `uint8`.

- [x] A decision on [[Project/Decisions]]
- [x] The same behaviour in both interpreters and both backends, with a parity or error-corpus program

## Evidence

- The owner's decision: trap at run time (D98). An integer cast to `char` that isn't a Unicode scalar (above 0x10FFFF, a surrogate, negative) is `runtime error: invalid char: <n> is not a Unicode scalar value` in both interpreters and `runtime error: invalid char` from both backends (a new trap, `__trap_char`, two compares; the IR's `check`), at the cast; casts from `uint8` aren't checked.
- At the boundaries (55295 and 57344 valid; -1, 55296, 57343, 1114112 trap) the four agree. Corpus `runtime_invalid_char.my` (interpreter message, native message, the span); two rows in `test_native_runtime`'s trap table, positions equal to the interpreter's.
