---
id: MYLA-122
title: Leave out retain and release of copies that are never written
type: improvement
status: review
priority: medium
labels: [ir, codegen, selfhost, performance]
---
Part of [[MYLA-109]]. Binding a value that owns heap memory copies and retains it, and the owner's end releases it ([[Architecture/IR]], "Lowering ownership"). When neither the copy nor the original is written, and the original outlives the copy, the pair cancels: the copy can borrow.

- [x] Which copies can borrow: a `let` of a part of a variable nothing writes while it lives (decided in the lowering, from the language's rules, not by an analysis over the IR; see How)
- [x] Their `retain` and `drop` left out; the verifier still accepts every function
- [x] Measured on the compiler compiling itself; the stress programs keep their memory bounds

## How

All in [[selfhost/lower.my]]. The IR can't tell whether a call writes through an aggregate's address it is given (a `var self`), so an analysis over it would have to assume the worst at every call. The language says it directly: a `let` is deeply immutable, and so is every parameter but `var self`.

- **Fixed variables.** `Local` records whether nothing writes the variable while it lives: a `let`, a parameter other than a `var self` receiver, a lambda's parameter or capture (its environment lives as long as the call), a `for` loop's element (borrowed from the loop's list, which doesn't change). `fixed_place` says whether an expression is a part of one: the variable, a field, a tuple's element, an element of a list or map in it.
- **Borrowing `let`.** A `let` whose value is such a place and isn't taken from an owned temporary keeps its copy but no reference: no `retain`, and its slot owns nothing, so no scope drops it. The copy can't change (a `let`), its source can't change (fixed), and the source outlives it (it is in scope where the `let` is, so its scope encloses the `let`'s). Whatever takes the value further (`return`, a `var`, a container, a capture) retains it as before. A `var`, or a `let` of a part of one, still owns.
- **`for` over a fixed variable.** The loop's list needs no reference of its own either.
- **Found on the way:** [[MYLA-123]], an argument read from the receiver of a `var self` method was changed or released by the method's writes; borrowing from parameters is only sound with that fixed.

## Evidence

- New test first: `test_lets_of_fixed_variables_borrow` failed with 13 `retain` and `drop` lines in a function taking `let`s of a parameter's fields, of an element of one, and a loop over one, and passes with none; the `let` of a `var`'s field keeps its owning slot. A method's `self` borrows, a `var self` doesn't (checked on the IR).
- The same source (the compiler) compiled before and after: 3,303.6 → 3,256.6 million instructions compiling itself (−1.4%), binary 1,247,328 → 1,239,136 bytes; wall time, 20 alternating runs: median 1.089 → 1.051 s (best 0.955 → 0.976 s, within the noise).
- The stress programs: the instruction counts are unchanged except lists (−0.6%), trait dispatch (−1.7%) and returning from a `for` loop (−0.3%); their wall times moved within the noise (sum of medians +1.6% with identical code in 18 of 21). Their memory-bound tests pass.
- Unit 595, integration 2, burn 739 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,245,809 bytes).

The biggest reference-counting costs left are copies the compiler's own code makes ([[MYLA-124]]).
