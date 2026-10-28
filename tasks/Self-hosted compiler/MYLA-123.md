---
id: MYLA-123
title: Arguments read from a `var self` receiver are changed by its writes
type: bug
status: review
priority: high
labels: [codegen, selfhost, ownership]
---
Found while planning [[MYLA-122]]. Both native backends pass an argument as the place it is read from: the value itself, or an aggregate's address, without a reference of its own. When the method takes `var self` and the argument is read from the same variable as the receiver, the method's writes reach the argument: `b.rename(b.name)` printed an empty string after `self.name = …` released the old string (a use after free), `b.swap(b)` saw its own writes in `other`, and `b.keep(b.xs)` saw the `push`. The interpreter, the language's semantics, passes a copy taken before the call.

- [x] A parity program (`method_arguments_survive_the_receivers_writes`) that fails on both backends
- [x] The self-hosted lowering stages such an argument (`stage`: a retained copy the statement drops)
- [x] The Python backend does the same (`_aliased_args`, released after the call)

## Evidence

- The parity program fails on both native backends without the fix (the self-hosted one printed an empty string, `qr`, `1` and `0` where the interpreter prints `ab`, `zzyy`, `2` and `2`; the Python one the same) and passes with it; reverting only the Python backend's change fails it again.
- Unit 595, integration 2, burn 738 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,270,593 bytes).
