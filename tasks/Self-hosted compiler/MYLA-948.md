---
id: MYLA-948
title: "`myla build`: a match arm that ends in `process.exit` inside a match used as a value is an internal error"
type: bug
status: todo
priority: medium
labels: [codegen, ir]
---
Found by [[MYLA-958]]. `myla check` and `myla run` accept this; `myla build` stops with `runtime error: internal error: main can't be lowered to the IR: a call without a value used as one --> selfhost/codegen.my:2863:32`.

```myla fragment
import std.process as process

fun get(n: int) -> Result<int, str> {
    if n > 2 { return Ok(n) }
    return Err("small")
}

fun main() {
    let v = match get(3) {
        Ok(b) => b
        Err(_) => {
            print("error")
            process.exit(1)
        }
    }
    print(v)
}
```

`process.exit` doesn't return (it ends a path, as `panic` does), so the arm needs no value; the lowering treats its call as one that must give one.

- [ ] A failing case in the native test suite first
- [ ] An arm ending in a call that never returns lowered as the checker types it (as `panic(…)` and `unreachable()` are)
