---
id: MYLA-526
title: "A method of a built-in type doesn't inline its module's small functions"
type: bug
status: done
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

- [x] A method of a built-in type counts as a function of the module that declares the `impl` for inlining (its IR name or the inliner's module test carries the module)
- [x] The reproduction's three methods have `bump`'s body natively; a `#test`-covered trap in an inlined helper still reports its own line

## Evidence

**What changed.** The inliner's module is the file of each function's declaration, not a part of its name. `take_ir` gets the node that declares the function (a function's `decl_id`, the impl's for a method; a lambda's node; a type's for a routine), the same node whose file the backends report a trap's position in, and `inline_small` copies a callee only when `CodeGen.module_of` gives both the same file (the index of its span, found by a binary search; -1, never inlined, for the prelude's nodes). `CodeGen.decl_of(name)` reads a function's `decl_id` without copying its signature. `same_module` (the comparison of names up to their last `$`) is gone from [[selfhost/inline.my]]. The rule stays: only functions of the caller's own file are copied, so a trap in a copy names the right file and line.

**The test** (`tests/burn/test_selfhost_codegen.py`, `test_a_builtin_types_method_inlines_its_modules_functions`): the reproduction, plus `ratio(a, b)` (a division) called by `impl [int] { fun per_first }`. It requires `13`, `25`, then `division by zero` at `m.my:6:` with exit 1, and no reference to `myla_pkg$m$bump` in `pkg$m$Box.bumped`, `__list.first_bumped` and `__list.len_bumped__4.i32`, nor to `myla_pkg$m$ratio` in `__list.per_first`.
- Before (the base `codegen.my` and `inline.my`): `FAILED (failures=1)`, `__list.first_bumped` ends in `jmp myla_pkg$m$bump`.
- After: `OK`, with `test_small_leaf_functions_are_inlined`.
- The reproduction by hand, natively on x86-64, on aarch64 (qemu), on wasm32 (Node) and interpreted: `13`, `25`, `runtime error: division by zero --> …/pkg/m.my:29:14`, exit 1 on all four. Neither `bump` nor `ratio` is referenced in the x86-64 or aarch64 binary any more: both are inlined everywhere.

**The benchmarks.** All 13 binaries are byte-identical before and after: none of them has a built-in type's method calling a small function of its own module on its path (quicksort has its own generic `sort`). `benchmarks/run.py`'s callgrind counts moved only by the executor's run-to-run variance (map_remove +3.0 %, closures +0.4 %, fannkuch −0.5 %, the same binaries).

**std.list's sorts** (a million `int`s of quicksort's sequence, callgrind, base compiler against this one, the same library):

| | Before | After | Change |
| --- | ---: | ---: | ---: |
| `sort` | 976.95 M | 976.35 M | −0.06 % (`run_end`'s 0.75 M gone) |
| `sort_by((p, q) => p < q)` | 1,212.30 M | 1,211.80 M | −0.04 % |
| `sort_unstable` | 512.85 M | 512.85 M | 0 (the same code) |
| `sort_unstable`, all of it by the heapsort (depth limit 0) | 2,176.44 M | 2,176.44 M | 0 |

**MYLA-480's heapsort helper.** The sift written with a helper `first_child(r, end)` (`if r >= end / 2 { return -1 }; return 2 * r + 1`, seven `#test` cases at the edge of `int`, all passing) took, heapsort only: 2,425.36 M with the base compiler (+11.4 %, MYLA-480's 11.7 %), 2,308.97 M with this one (+6.1 %): inlined now, but `end / 2` is computed on every step and the -1 tested a second time. `first_child(r, half)` with `half` computed once: 2,238.53 M (+2.9 %). Neither is free, so the comparison stays inline; its comment in [[lib/std/list.my]] now gives these numbers instead of the old reason.

**The compiler compiling itself** (`build/stage3 selfhost/gen_main.my lib`, callgrind):
- the base compiler on its own source 9,943.34 M, this one on its own 9,944.43 M (+0.011 %, the new source has more to compile);
- both on this source: 9,946.22 M against 9,944.43 M (−0.018 %).
- A first version, `self.module_file(self.sig_of(name).decl_id)` with a linear walk of the spans for a path, cost +22.3 M (+0.22 %): the walk, the copied signature, and a copy of the whole `CodeGen` the lowering staged for the outer call (filed as [[MYLA-542]]). The binary search over span indices and `decl_of` took it back.
- Its text 2,145,872 → 2,145,979 bytes (+107); the binary's file 5,511,760 → 5,516,448 bytes (a page more of alignment; the data +208 bytes is the library comment the compiler embeds). The bootstrap's byte-identical fixed point holds (`stage2.s` = `stage3.s`, 23,741,310 bytes).

**Suites.** `scripts/test.sh fast`: `Ran 855 tests … FAILED (failures=1, skipped=3)`, the failure `test_embedded_std.test_the_module_is_what_lib_gives` (expected: the comment in `lib/std/list.my` is ahead of `selfhost/embedded_std.my` until the integrator's seed commit). `tests.burn.test_selfhost_codegen` and `tests.burn.test_compiler_parity`: `Ran 300 tests … OK`. `build/myla test lib/std/list.my --stdlib lib`: `24/24 passed.` interpreted, `--native`, `--native --target aarch64-linux` and `--native --target wasm32-wasi`. `build/myla test selfhost/codegen.my --only module_of` 2/2, `--only decl_of` 1/1, `selfhost/inline.my` 5/5.
The full `scripts/test.sh` (on the final source, after its bootstrap): `Ran 1532 tests … FAILED (failures=1, skipped=341)`, the same expected `test_embedded_std` failure.

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]].
