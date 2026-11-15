---
id: MYLA-724
title: "The interpreter's print clears the cause __io_errno reads"
type: bug
status: todo
priority: low
labels: [interpreter, runtime]
---
Found by [[MYLA-704]] (2026-11-15, at `194c9dc` and after). Interpreted, a `print` sets the cause `__io_errno()` reads back to 0; natively it leaves it as the last primitive set it. std's modules read the cause right after the primitive, so a program sees it only through the primitives (`#allow(primitive)`), but the interpreter and native code should agree (D191's parity).

```
#allow(primitive)
fun main() {
    let r = __seek(12345, 0, 0)
    print(r)
    print(__io_errno())
}
```

`myla build` (x86-64 Linux, and Windows under Wine): `-1`, `34` (BAD_HANDLE). `myla run`: `-1`, `0`.

- [ ] The interpreter's `print` (and the other writes of the standard streams that don't fail) leave `__io_errno` as it was, as std.rt's do; a parity case in `tests/burn/test_platform_primitives.py`
