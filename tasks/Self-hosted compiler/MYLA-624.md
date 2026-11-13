---
id: MYLA-624
title: "A deep type the program writes, wrapped once more by a generic call, is refused by `myla build` as polymorphic recursion"
type: bug
status: todo
priority: low
labels: [lowering, generics, round-6]
---
Found by the checker-and-loader lane of round 6's follow-up ([[MYLA-543]]). The lowering's limit on instances (`Lower.call_target`, [[Architecture/Monomorphization]]) refuses an instance already at the limit (type arguments 64 types deep) that asks for a deeper one. Since [[MYLA-543]] it only refuses one deeper than the asking instance's own, so a recursion over a written 65-deep type that passes it on unchanged builds. A finite program that wraps such a type once more in a generic call is still refused:

```
fun wrap<U>(x: U) -> [U] {
    return [x]
}
fun outer<T>(x: T) -> int {
    return wrap([x]).len()
}
fun main() {
    let x: [[…64 deep…[int]…]] = [[…[5]…]]
    print(outer(x))
}
```

`myla check` says `ok` and `myla run` prints `1`; `myla build` says `type error: the instances of 'wrap' nest without end: this call asks for one whose type arguments are 65 types deep (the limit is 64)` at `wrap([x])`. Generate it with 64 nested lists (Python: `t = "int"; for _ in range(64): t = f"[{t}]"`). Base `aef0b21` with [[MYLA-543]]'s change.

Since [[MYLA-543]] the checker refuses every polymorphic recursion it can see, so the lowering's limit only has to catch a recursion through a trait's method. Proposal: give each queued instance (`MonoFn`, [[selfhost/codegen.my]]) the chain of functions that asked for it (the lambdas', partial applications' and function values' jobs the chain of the function they belong to), and refuse a call past the limit only when its callee is in the asking instance's chain: a recursion. Then no finite program is refused, whatever types it writes.

- [ ] A call past the limit is refused only when it is part of a recursion (its callee among the instances that led to it)
- [ ] A parity program with a written 64- and 100-deep type wrapped once and twice by generic calls; the polymorphic recursions through a trait of `test_polymorphic_recursion_through_a_trait_is_refused_by_the_build` still refused
