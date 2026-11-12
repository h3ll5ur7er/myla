---
id: MYLA-542
title: "`self.f(self.g(k))` in a `var self` method copies the receiver for `f`"
type: improvement
status: todo
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

- [ ] A method call on the variable counts as a write only when the method takes `var self` (or the receiver's type isn't known), so `nested` lowers like `split`
- [ ] The self-compile's instructions before and after, and the copies of `CodeGen` left in `build/stage3.s`
