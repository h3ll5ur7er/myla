---
id: MYLA-42
title: Rust edition has no static checking
type: feature
status: backlog
priority: medium
labels: [rust, sema]
---
`myla-sema` builds declaration tables and checks mutability, nothing more: there is no type checking and no name resolution. Type annotations are parsed and ignored (`let x: int = "hello"` runs and prints `hello`), an unknown name is a runtime error (the corpus expects exactly that), and generics run by erasure with bounds and `typealias` recorded but unused.

The Python and self-hosted toolchains check statically; this is the biggest semantic difference of the Rust dialect ([[Architecture/Rust-edition]]).

## Done when

- [ ] Decide whether the Rust edition is meant to stay "lightly typed" (then say so in its spec) or to gain a checker
- [ ] At minimum: name resolution, arity checks and literal range checks at compile time
