---
id: MYLA-801
title: "Checker: an async method in a trait's impl is accepted and called without `await` (H3)"
type: bug
status: review
priority: high
labels: [checker, traits, concurrency, round-7]
---
Found by [[Project/Review-2026-11-17]] (H3, older than `547339a`); filed by [[MYLA-790]]. A trait's method is called without `await`: by its operator (`+`, `*`, `-x`, `x[i]`, `x[i] = v`, D200), by `==` and `<` (`Eq`, `Ord`), by a format hole (`Format`), by a map key (`Hash`) and through a bound (`t.f()` on a `T: Tr`). An impl could still make it `async`, and the call then ran the async function from plain code:

```myla error
import std.task as task

struct V {
    x: float,
}

impl Add for V {
    async fun add(self, k: V) -> V {
        await task.sleep(1)
        return V { x: self.x + k.x }
    }
}

fun main() {
    let v = V { x: 3.0 }
    print((v + v).x)
}
```

`myla check` said `ok`; `myla run` printed 6, native code (x86-64, `--checked`, aarch64) crashed, and wasm32 failed with the internal error `myla_V.add takes 1 words, called with 3`. A user trait's impl took an `async fun` the same way.

D256: `async` on a trait impl's method is refused where the trait's method isn't async, which today is every trait's (a trait has no async methods, until [[MYLA-434]] designs them).

- [x] The checker refuses it where it compares the impl with the trait (`check_trait_conformance`): `method 'add' in impl of trait 'Add' for 'V' can't be 'async': the trait's method isn't, and it is called without 'await'`
- [x] Tests: `examples/errors/type_impl_async_operator_method.my` (the reproducer); `tests/burn/test_operator_traits.py`'s errors for `Index`, `Eq`, `Format` and a user trait
- [x] Docs: the operators page and [[Language/Methods-and-traits]] say it

## Evidence

- Before (BASE `fe30af6`): `myla check` of the reproducer and of the same with a user trait `trait Size { fun size(self) -> int }` and `async fun size` printed `ok`.
- After: both are the type error above, at the method; `tests.burn.test_error_corpus` and `tests.burn.test_operator_traits` pass. No module of `lib/std` has such a method (the bootstrap and `myla test` of the library's modules pass unchanged).
