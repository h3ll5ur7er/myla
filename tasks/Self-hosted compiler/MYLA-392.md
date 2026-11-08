---
id: MYLA-392
title: "Native: an await in a match nested in a match arm can't be lowered"
type: bug
status: backlog
priority: medium
labels: [lowering, async, native]
---
Found by the `std.http` lane ([[MYLA-347]]). An `await` inside a `match` nested in another `match`'s arm, matching on that arm's binding, stops `myla build` with "internal error: worker can't be lowered to the IR: a function used as a value" (from `name` in [[selfhost/lower.my]]). The interpreter runs it.

```myla fragment
import std.task as task

enum Cause { Stop, Code(int) }

async fun worker(r: Result<int, Cause>) -> int {
    match r {
        Ok(n) => { return n }
        Err(e) => {
            match e {
                Stop => {}
                Code(code) => {
                    print(code)
                    await task.sleep(1)
                }
            }
        }
    }
    return 0
}

#main
async fun main() { print(await worker(Err(Cause.Code(24)))) }
```

`std.http` decides outside the inner match (`accept_fate`, `answerable`) instead.

- [ ] Root cause (the async split's handling of a binding of an outer arm, `anf.my` or the frame lowering), a fix, the program above as a parity program on every target
