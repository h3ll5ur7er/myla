---
id: MYLA-435
title: "A failing expect points at its caller"
type: improvement
status: in-progress
priority: low
labels: [std, diagnostics]
---
[[MYLA-324]]'s follow-up from [[Project/Review-2026-11-09]]: `opt.expect("…")` failing reports a position inside `lib/std/option.my`, not the call.

Reproducer (checked 2026-11-13, [[MYLA-554]]):

```myla fragment
fun find(xs: [int], v: int) -> Option<int> {
    for i in 0..xs.len() {
        if xs[i] == v {
            return Some(i)
        }
    }
    return None
}

fun main() {
    let at = find([1, 2, 3], 7).expect("7 is in the list")
    print(at)
}
```

`myla run`, and the binaries of `myla build`, `myla build -g` and `myla build --checked`, all print the `panic` inside `Option.expect` and exit with status 1:

```
runtime error: 7 is in the list
  --> <myla>/std/option.my:79:26
```

where the caller's position is `expect.my:11:33`. `Result.expect` fails the same way, at `option.my:153`.

There is no `unwrap` in Myla (the skill says to write `expect`, `unwrap_or` or a `match`; [[Language/Standard-library/Option]] has no `unwrap` either); the functions of std.option that end in a `panic` of their own are `Option.expect` and `Result.expect`.

- [ ] A way for a library function to report its caller's position (as Rust's `#[track_caller]`), on every runner
- [ ] `Option.expect` and `Result.expect` use it, and the error-corpus or parity tests pin the caller's position for both, interpreted and natively
