---
id: MYLA-123
title: Arguments read from a `var self` receiver are changed by its writes
type: bug
status: in-progress
priority: high
labels: [codegen, selfhost, ownership]
---
Found while planning [[MYLA-122]]. Both native backends pass an argument as the place it is read from: the value itself, or an aggregate's address, without a reference of its own. When the method takes `var self` and the argument is read from the same variable as the receiver, the method's writes reach the argument: `b.rename(b.name)` printed an empty string after `self.name = …` released the old string (a use after free), `b.swap(b)` saw its own writes in `other`, and `b.keep(b.xs)` saw the `push`. The interpreter, the language's semantics, passes a copy taken before the call.

- [ ] A parity program (`method_arguments_survive_the_receivers_writes`) that fails on both backends
- [ ] The self-hosted lowering stages such an argument (`stage`: a retained copy the statement drops)
- [ ] The Python backend does the same (`_aliased_args`, released after the call)
