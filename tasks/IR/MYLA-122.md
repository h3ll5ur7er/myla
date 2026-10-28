---
id: MYLA-122
title: Leave out retain and release of copies that are never written
type: improvement
status: in-progress
priority: medium
labels: [ir, codegen, selfhost, performance]
---
Part of [[MYLA-109]]. Binding a value that owns heap memory copies and retains it, and the owner's end releases it ([[Architecture/IR]], "Lowering ownership"). When neither the copy nor the original is written, and the original outlives the copy, the pair cancels: the copy can borrow.

- [ ] An analysis over the IR: owning slots whose value is a retained copy of another place, neither written while both live (liveness from [[MYLA-121]], writes through `cow`, stores and calls taking a `var self`)
- [ ] Their `retain` and `drop` left out; the verifier still accepts every function
- [ ] Measured on the compiler compiling itself; the stress programs keep their memory bounds
