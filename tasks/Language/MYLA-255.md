---
id: MYLA-255
title: Function parameters with default values
type: feature
status: backlog
priority: low
labels: [language, ergonomics, design]
---
The owner's idea (2026-11-03), for after the runtime's port ([[MYLA-162]]): a parameter with a default value, which a call may leave out.

```myla
fun connect(host: str, port: int = 80, retries: int = 3) -> Conn { … }

connect("example.org")             // port 80, retries 3
connect("example.org", 8080)       // retries 3
```

Questions for the design round (a decision before the implementation):
- **Which arguments can be left out:** only trailing ones (positional, as C++ and Python without keywords), or with named arguments too (`connect("x", retries: 5)`, as Swift and Kotlin)? Myla has no named arguments yet; adding them is a decision of its own and changes what a call looks like everywhere.
- **What a default may be:** a constant expression only (simplest, and the same value every call), or any expression evaluated at each call, in the callee's scope (seeing earlier parameters?) or the caller's? Python's evaluated-once mutable default is the trap to avoid; Myla's values are immutable, which removes most of it.
- **Function values and types:** does `(str, int) -> Conn` hold `connect`, and can a call through a function value leave arguments out? (Swift: no, defaults belong to the declaration.) Partial application (`connect(_, 8080)`) and `|>` must stay unambiguous.
- **Methods, traits and generics:** may a trait's method declare defaults; must an `impl` repeat them; can a default mention a type parameter?
- **Lowering:** the caller fills in the missing arguments, so the callee and its calling convention (D119) stay as they are; `become` (D87) and the stack-word rule count the filled-in arguments.
- **Interplay:** overloads don't exist in Myla, so no ambiguity there; the checker's messages for a wrong number of arguments name the defaults; the LSP's signature help shows them.

- [ ] Design round and a decision (D-number), the examples and errors on [[Language/Functions]]
- [ ] Parser, checker, lowering, interpreter; error-corpus examples; the tree-sitter grammar and the editor
