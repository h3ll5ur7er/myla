---
id: MYLA-389
title: "wasm32: releasing a deeply nested value overflows the stack"
type: bug
status: backlog
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

- [ ] Find why the enum path recurses deeper per level than the struct path (frame size of the drop routine?) and release iteratively, or with a bounded stack, on every target
- [ ] The program above in the wasm32 suite at 100,000 levels
