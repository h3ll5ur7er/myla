---
id: MYLA-526
title: "A method of a built-in type doesn't inline its module's small functions"
type: bug
status: todo
priority: low
labels: [ir, optimisation, inlining]
---
Found by [[MYLA-480]]. [[MYLA-162]]'s inliner copies a small leaf function into its callers of the same module, which `same_module` ([[selfhost/inline.my]]) decides by the part of the two IR names before their last `$`. A method of a built-in type is named after the type, not the module (`___list.sort__4.i32`, `___list.first_bumped`), without a `$`, so it never counts as the module's own and calls each helper. A struct's method (`pkg$m$Box.bumped`) inlines it.

Reproduction: a module `pkg/m.my`

```myla fragment
fun bump(n: int) -> int {
    if n > 100 { return n }
    return n + 1
}

struct Box {
    v: int,
}

impl Box {
    fun bumped(self) -> int {
        return bump(self.v)
    }
}

impl [int] {
    fun first_bumped(self) -> int {
        return bump(self[0])
    }
}

impl<T> [T] {
    fun len_bumped(self) -> int {
        return bump(self.len())
    }
}
```

and a `main.my` beside `pkg/` with `from .pkg.m import Box` and `print(Box { v: 3 }.bumped() + [5].first_bumped() + [1, 2].len_bumped())`. `build/myla build main.my` and `objdump -d`: `myla_pkg$m$Box.bumped` has `bump`'s body, `myla___list.first_bumped` and `myla___list.len_bumped__4.i32` end in `jmp <myla_pkg$m$bump>`.

The cost where it matters: std.list's sorts are such methods. A helper call in `sort_unstable`'s heapsort sift took 11.7 % more instructions (MYLA-480 wrote the comparison inline instead), and `sort`'s run loop pays about 0.2 % for its `run_end` call.

- [ ] A method of a built-in type counts as a function of the module that declares the `impl` for inlining (its IR name or the inliner's module test carries the module)
- [ ] The reproduction's three methods have `bump`'s body natively; a `#test`-covered trap in an inlined helper still reports its own line
