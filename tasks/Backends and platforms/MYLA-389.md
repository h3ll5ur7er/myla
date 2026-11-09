---
id: MYLA-389
title: "wasm32: releasing a deeply nested value overflows the stack"
type: bug
status: review
priority: medium
labels: [wasm32, runtime, memory]
---
Found by the `std.xml` lane ([[MYLA-348]]). A value nested about 2,000 levels deep through an enum and a list is released recursively, and on wasm32 that overflows the stack; natively it doesn't. A `struct Box { kids: [Box] }` of the same depth is fine.

```myla fragment
enum Node { Elem(El), Text(str) }
struct El { name: str, kids: [Node] }

fun nest(n: int) -> El {
    var b = El { name: "a", kids: [Node.Text("x")] }
    for k in 0..n { b = El { name: "a", kids: [Node.Elem(b)] } }
    return b
}

fun main() {
    let b = nest(3000)
    print(b.kids.len())
}
```

On wasm32 it prints `1`, then `runtime error: stack overflow`. `std.xml`'s `deep` test uses 1,000 levels because of it.

- [x] Find why the enum path recurses deeper per level than the struct path (frame size of the drop routine?) and release iteratively, or with a bounded stack, on every target
- [x] The program above in the wasm32 suite at 100,000 levels

## Why the enum path was deeper

`[Node]` holds each `Node` inline (24 bytes: the tag and an `El`), so the list's slow path calls the enum's release walk `__walkd_Node`, which calls the struct's `__walkd_El`, which releases `kids` through `__drop_list_Node` (its entry a jump to the slow path): three frames a level. `Box { kids: [Box] }` has one pointer member, whose walk is inlined into `__drop_list_Box_slow`: one frame a level. Either way the release was a recursion as deep as the value: wasm32's engine stack (Node's, about 1 MB) ran out at 1,840 levels of the `Node` path and 3,911 of `Box`'s; under qemu the 8 MiB aarch64 stack at fewer than 100,000; natively the main thread survived only because its stack may grow to 120 MiB (a million levels worked), while a worker's 8 MiB stack (tasks) overflowed at 100,000.

## The fix: a bounded stack

A cell type that can nest itself without bound (`CodeGen.drop_reenters`: a list, map, boxed enum or actor whose members reach a cell of its own type) gets a guarded slow path (`drop_guard`/`drop_guard_end` in [[selfhost/lower.my]]): it counts the guarded releases running inside one another on the worker (`__drop_depth`); past `DROP_DEPTH` (64) it puts the cell on the worker's deferred cells (`__drop_defer`, linked through the dead cells' count words as `next << 16 | kind`) and returns. The outermost guarded release, back at depth 0, finds them and calls `__drop_drain`, which releases them one at a time through `__drop_routines` (each kind's slow path, by `call_code`) until none is left. The two runtime variables are in `.bss`, and per worker with tasks (`tls_offset` 80 and 112); they are the compiler's own (no std.rt code reads them), so the seed needn't carry them first. Types that can't nest themselves are untouched.

Cost: on `benchmarks/binary_trees` (a recursive enum released millions of times) 9.4% more instructions (686.5 M to 751.0 M at size 14, callgrind; the seed against this compiler), about 8 per release; the wall time at size 18 is the same within noise (2.15 s and 2.11 s, 1.97 to 2.05 s over runs).

## Evidence

- Before: the task's program on wasm32 printed `1`, then `runtime error: stack overflow` (at 3,000 levels; the bisected limits above); at 100,000 levels `Box` and `Node` overflowed on wasm32 and aarch64 (qemu); the tasks program (8 children each building and releasing a 100,000-deep `Node` tree, `MYLA_THREADS=4`) compiled by the seed: `runtime error: stack overflow` natively.
- After: `test_deep_values_are_released_in_a_bounded_stack` in [[tests/burn/test_selfhost_codegen.py]]: 100,000 levels through `Node`/`El`, `Box`, two recursive enums and 20,000 through a map, ten rounds, peak 39.5 MB natively and 56.2 MB of wasm32 linear memory (the same as one round: the cells are reused), and the tasks program; passes natively, with `MYLA_TEST_TARGET=aarch64-linux` and with `MYLA_TEST_TARGET=wasm32-wasi`. Natively a million levels of `Node` and `Box` release too.
- The bootstrap reaches its fixed point.
- `std.xml`'s `deep` test keeps 1,000 levels (interpreted, 100,000 take a minute); its comment no longer blames the release.
