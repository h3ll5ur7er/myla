---
id: MYLA-542
title: "`self.f(self.g(k))` in a `var self` method copies the receiver for `f`"
type: improvement
status: review
priority: low
labels: [ir, optimisation]
---
Found by [[MYLA-526]]. In a method that takes `var self`, a call on `self` whose argument calls another method on `self` stages a copy of the receiver (a `__staged` slot: `copy`, `retain`, then `drop`) before evaluating the argument, even when neither method takes `var self`. `later_writes` ([[selfhost/lower.my]], [[MYLA-237]]) asks `may_write_expr` ([[selfhost/codegen.my]]), which counts every method call on the variable as a possible write, whatever its receiver's mode.

Reproduction:

```myla fragment
struct S {
    names: [str],
    n: int,
}

impl S {
    fun g(self, k: int) -> int {
        return k + self.names.len()
    }

    fun f(self, k: int) -> int {
        return k * 2 + self.n
    }

    fun nested(var self, k: int) -> int {
        self.n += 1
        return self.f(self.g(k))
    }

    fun split(var self, k: int) -> int {
        self.n += 1
        let j = self.g(k)
        return self.f(j)
    }
}
```

`--emit-ir` shows `nested` with `$2 __staged: S (16 bytes) owns`, `copy 16 [%t7], [%t6]`, `retain S [%t7]` before `call myla_S.g` and `drop S $2` after `call myla_S.f`; `split`, the same work, has none of it. On a large receiver it costs: the compiler's own code has 78 such copies of `CodeGen` (135 words, `rep movsq`, then `__walkr_codegen$CodeGen` and `__walkd_codegen$CodeGen` over every field) and 3 of `Checker`, and the walks alone take about 20 M of the 9,945 M instructions of the compiler compiling itself (`__walkr`/`__walkd` of `CodeGen` 7.8 M each, of `Checker` 2.6 M each). [[MYLA-526]]'s first version of `inline_small` (`self.module_file(self.sig_of(name).decl_id)`) made one more on every call instruction, which is how it showed up.

- [x] A method call on the variable counts as a write only when the method takes `var self` (or the receiver's type isn't known), so `nested` lowers like `split`
- [x] The self-compile's instructions before and after, and the copies of `CodeGen` left in `build/stage3.s`

## What changed

- `may_write_expr` and its family ([[selfhost/codegen.my]]) take the code generator; a method call on the variable counts as a write only when the method it calls takes `var self`, or is a builtin that changes its receiver (`push`, `pop`, `remove`, `append`, …), or isn't a method the program declares (`CodeGen.method_may_write`). So `later_writes` stages no copy for `self.f(self.g(k))`, a match's scrutinee copy owns references only when an arm may really write the variable, and the operands [[MYLA-543]]'s B2 holds (`written_after`) are held only then: `r[r.len() - 1]` holds nothing.
- The other source of copies of `CodeGen` was H4's ([[MYLA-415]]): a `var self` method whose arguments may change its receiver's variable had every argument computed first into a local of its own, a plain `cg` too (`lw.entry_member(cg, lw.read_cell(sm), …)`, 38 of the copies left after the first change). A variable, or a field of one, that no later argument writes (`field_path`, `written_after`) is now passed as it is: it reads the same where it is passed.

## Evidence

- `test_a_method_taking_self_writes_nothing` (`test_selfhost_codegen`): the IR of the reproduction; `nested` had `__staged: S (16 bytes) owns`, `copy 16`, `retain S` and two `drop S` (31 lines) and has none (25 lines; `split` 30); a `var self` method in the argument (`self.f(self.bump(k))`) still stages one.
- `build/stage3.s`: copies of `CodeGen` (135 words, `rep movsq`) **77 → 1** (the one left stores `cg` in an `LDefer`), calls of `__walkr_codegen$CodeGen` 78 → 2 and of `__walkd_` 79 → 3; of `Checker`'s 3 → 0 and 5 → 2. With the first change alone, 37.
- The compiler compiling the compiler of 6e699ca (the same input for both, cachegrind): the compiler of 6e699ca **10,122.8 M** instructions, this branch's **9,137.0 M** (−9.7 %); 9,173.3 M with the first change alone. Its output is smaller (23,962,277 → 23,917,530 bytes).
- The benchmarks' code is unchanged, function by function ([[MYLA-543]]'s evidence); four examples got shorter (`std.num.f64_literal_bits` 248 → 244 instructions, `str.split` 18 → 5, `str.splitn` 245 → 238).
- The review's generators `gen_h4.py` (1,905, 1,905 and 1,596 lines) and `gen_loc.py` (9 programs) and `gen_rd.py` (89 forms): the interpreter's output natively after both changes; `test_compiler_parity` (with H4's `keys_that_change_their_container`): OK.
