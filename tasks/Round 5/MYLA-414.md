---
id: MYLA-414
title: "P1 The interpreter: generic code, receivers, errno"
type: bug
status: todo
priority: high
labels: [interpreter, generics, overflow, round-5]
---
Work package P1 of [[Project/Review-2026-11-09]] (wave A1), with round 4's additions from [[Project/Review-2026-11-10]]. Files: `selfhost/interp.my`. Reopens [[MYLA-395]] and [[MYLA-391]]. Start by turning each reproducer into a failing test.

- [ ] H1: arithmetic, comparison and formatting typed by a type parameter use the concrete type: bind type parameters in frames for every generic call, then trap (D175), wrap and compare as elsewhere; `float32` too (`[uint64].sorted()`, `xs.sum(0)`, generic `100i8 + 100i8`, `less(0u64, MAX)`)
- [ ] Tests: `test_overflow` with a `T: Add` function, `xs.sum(0)` and `iter.sum`; a differential test of generic code per integer width, interpreted against native
- [ ] H6 and M4: one "evaluate the receiver as a place" path instead of a case per receiver shape (`var self` on `xs[i]`, `m[k]`, a field of a call's result of type-parameter type)
- [ ] An unresolved method is a runtime error with its position, never the printed value `ERR: VUnit` with exit 0
- [ ] M5: reset the errno after a captured write (`myla test /absolute/path.my` with a printing case)
- [ ] M8, the interpreter's half: a list or tuple `Err` of a test function prints its value, not `ERR: VList()`
- [ ] L3: an actor's method calling the actor's own field that holds a function
- [ ] L4: a `char` literal typed `uint8` (`let x: uint8 = 'a'`) prints as the number
- [ ] S2: `__read_bytes` and `__write_bytes` without a boxed value per byte (interpreted `io.copy` of 32 MB: 2,096 ms, 27 ms before D177)
- [ ] [[MYLA-380]]'s follow-up: interpreted `next` is 8 to 22 times a plain loop; measure and take what is cheap
