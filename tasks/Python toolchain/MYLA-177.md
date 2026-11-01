---
id: MYLA-177
title: "`as char` is unchecked: surrogates and values above 10FFFF"
type: bug
status: todo
priority: medium
labels: [checker, chars, parity]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). `char` is documented as a Unicode scalar, but `0xD800 as char` and `0x110000 as char` are accepted: printing the first crashes the interpreter with `UnicodeDecodeError`, native code prints three garbage bytes; the second prints 1114112 as an integer. The checker, the interpreter and the code generator each say the cast is unchecked. Needs a decision: trap at run time (like an out-of-range index), saturate (D59's answer for floats), or forbid the cast from integers wider than `uint8`.

- [ ] A decision on [[Project/Decisions]]
- [ ] The same behaviour in both interpreters and both backends, with a parity or error-corpus program
