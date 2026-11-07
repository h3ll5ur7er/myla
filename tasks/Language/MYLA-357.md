---
id: MYLA-357
title: "myla test --native: a case whose receiver is an empty list doesn't build"
type: bug
status: todo
priority: medium
labels: [testing, native, harness]
---
Found by the `std.list` lane ([[MYLA-323]]). A `#test` case on a method of a list impl whose receiver is `[]` passes in the interpreter, but `myla test --native` stops. The generated harness writes `var __recv = []` without the receiver's type, so it fails with "cannot infer the element type of an empty list `[]`", at a position past the file's end.

```myla fragment
impl [str] {
    #test([], "-")[1]
    #test(["a"], "-")[2]
    fun width(self, sep: str) -> int { return self.len() + sep.len() }
}
```

The `std.int` lane ([[MYLA-322]]) found a second problem in the harness: it types an unsuffixed literal receiver as `int32`, so `#test(5)[…]` on a method of `impl int8` doesn't build natively. Its cases suffix every receiver (`5i8`).

A smaller thing seen in the same place: a case on a method of `impl [str]` is reported as `__list.width #1`, the internal name, where `[str].width #1` would read better (D116 names a case by the method's checked name).

- [ ] The harness ([[selfhost/harness.my]]) annotates every receiver and argument it binds with the parameter's type, which covers both: `[]` and an unsuffixed literal
- [ ] A case of every receiver kind with an empty value (`[]`, `[:]`) in `test_test_functions` or the harness's own tests, interpreted and native
- [ ] The report's name of a method on a built-in type
