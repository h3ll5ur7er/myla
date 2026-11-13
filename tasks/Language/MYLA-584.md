---
id: MYLA-584
title: Operators between different types (operator traits with type arguments)
type: feature
status: review
priority: high
labels: [language, checker, design]
---
Vector, matrix and quaternion code ([[MYLA-587]]) is unreadable without operators between different types: `v * 2.0`, `2.0 * v`, `m * v`, `q * v`, `-v`. Today it can't be written:

- An operator trait combines two values of one type: `Mul` is `fun mul(self, other: Self) -> Self` (`register_builtin_op_traits` in [[selfhost/checker.my]]), and `infer_overload_known` refuses `operator '*' requires both operands to have the same type`.
- A type has one impl per trait (`duplicate impl of trait … (at most one user impl per trait/type pair)`) and one method per name, so a second `mul` is `duplicate method 'mul' for type 'V'`. The operator is dispatched by that name: `method_sig(type_key(lt), arith_method(op))`.
- There is no trait for unary `-` (`unary '-' requires a numeric operand`), so `-v` can't be written either.

The same limit hurts outside graphics: `BigInt + int64`, `Duration * int`, `Money * int`, complex numbers.

## Goal

```myla fragment
let w = 2.0 * (m * v + offset) - n * dot(v, n) * 2.0
q = q * Quat.axis_angle(axis, dt)
pos += vel * dt
```

…in user code, with the operators' meaning in the library (`std.vector`, `std.matrix`, `std.quaternion`) and checked statically; and generic code that names what it needs: `fun lerp<T: Add + Mul<float, T>>(a: T, b: T, t: float) -> T`.

## Options

**A. Operator traits with type arguments for the right operand and the result (recommended).** `Add<R, O>`, `Sub<R, O>`, `Mul<R, O>`, `Div<R, O>`, `Rem<R, O>`: `fun mul(self, other: R) -> O`.

- `impl Mul<float, Vec3> for Vec3 { fun mul(self, k: float) -> Vec3 { … } }`, `impl Mul<Vec3, Vec3> for Mat3`, `impl Mul<Vec3, Vec3> for float64` (the scalar on the left: an impl on the built-in float, beside its built-in `float * float`).
- Shorthands keep every program working: a bare `Mul` is `Mul<Self, Self>`, `Mul<R>` is `Mul<R, Self>`. Existing impls and bounds (`T: Add`) don't change.
- Coherence: at most one impl per trait, `Self` and `R`; `O` follows from them. `a * b` takes the impls of `Mul` for `a`'s type and picks by `b`'s type; the choice is recorded per node for the interpreter and the lowering, which call it like any method.
- New: `Neg<O>` (`fun neg(self) -> O`, bare `Neg` = `Neg<Self>`) for unary `-`.
- Compound assignment needs nothing more: `v *= 2.0` is `v = v * 2.0` (D104), allowed when the result is `v`'s type.
- `Eq` and `Ord` stay same-type.
- Precedent: Rust's `Mul<Rhs>` with `Output`, but as a type argument instead of an associated type (Myla has none, D55/D171).
- Cost: checker (built-in traits with type parameters, impl keying by arguments, operator resolution, bound solving, messages), the method table (operator methods get an internal name per right-hand type, say `Vec3.mul<float64>`), interpreter and lowering (dispatch from the recorded choice), monomorphization of bounded generic code. Backends unchanged.

**B. Right operand only, `Mul<R>`, result from the impl's signature.** Shorter impls, but generic code can't say what `a * k` is through `T: Mul<float>`. A is B plus a result argument, and A's shorthand `Mul<R>` gives B's spelling for the common case.

**C. Overloading of functions and methods by parameter types** (Swift's `static func *`). The most general, but it reaches everything: lambdas without annotations, partial application, function values, `|>`, error messages. Out of proportion for this need and against Myla's one-name-one-meaning rule.

**D. Overloading only for operator functions** (`fun op_mul(a: Vec3, k: float) -> Vec3`, free and overloadable). A's resolution without A's traits: generic code can't name the operators it needs. Worse than A.

**E. Built-in small vector types in the compiler** (`float32x4`, elementwise operators, SIMD). Fast, but closed: no `Quat`, `Complex`, `BigInt`, `Money`. A possible later optimisation under `std.vector`, not the answer to readability.

## Open questions for the owner

- [x] Choose an option (recommendation: A) and record it as a decision: A, D198 (2026-11-13)
- [x] A literal beside a non-literal operand: `v * 2` with only `Mul<float64, Vec3>` is an error; write `2.0` (the owner, 2026-11-13)
- [x] `Neg` and an `Index` trait in this round (the owner, 2026-11-13): `Index<I, O>` for `v[i]`, `IndexSet<I, V>` for `v[i] = x`; `m[r, c]` syntax is not part of it (`m[(r, c)]`)

## Steps (for A)

- [x] Checker: the operator traits with type parameters and shorthands, `Neg`, conformance of impls, impls keyed by trait, `Self` and `R`, operator resolution by both operands' types, bounds `T: Mul<R, O>` in generic code, messages that name the missing `impl Mul<R, O> for T`
- [x] Interpreter and lowering: call the recorded impl; unary `-` through `Neg`
- [x] Tests first: a burn test of mixed-type operators run interpreted and natively (and in `test_aarch64.PROGRAMS`), error-corpus files for a missing impl, an ambiguous impl pair and a non-`Self` result through `+=`
- [x] Docs: [[Language/Methods-and-traits]], [[Language/Generics]], [[Language/Expressions-and-operators]], the decision, the skill (`builtins.md`, the habits table)
- [x] Bootstrap fixed point; a seed staged before `lib/std` uses it ([[.claude/skills/myla/reference/compiler.md]], "Bootstrap and seeds")

## Evidence

- Built as option A (D198), with `Neg<O>`, `Index<I, O>` and `IndexSet<I, V>`. No AST node: the checker keeps `op_impls` (the impls by type arguments, their methods renamed `mul$float64` in the declarations too) and records each operator that calls one in `op_sites` (`IndexSet` targets in `op_sets`: a compound assignment's target node is also its value's left operand, which first overwrote the write's entry: `p[0] += 1.5` did nothing until they were kept apart). The interpreter calls the method through `eval_method_call`, the lowering through `direct_call`; generic code picks the impl by the instance's types (`find_op_impl`). The classic same-type impl keeps its old path in all three stages.
- Tests first: `tests/burn/test_operator_traits.py` failed before the change (`trait 'Mul' expects 0 type argument(s), got 1`, `unknown trait 'Neg'`, …) and passes after: 3/3 (the program and an async one alike interpreted and natively, 11 error cases). The program also prints the same as a `wasm32-wasi` module under Node, and builds for `aarch64-linux` (no qemu here: registered in `test_aarch64.PROGRAMS` and `_targets.py` for CI).
- Error corpus: `type_op_int_literal_for_float`, `type_op_impl_duplicate_right_operand`, `type_op_impl_generic_right_operand`, `type_index_set_missing`, `type_neg_missing`, pinned; `test_error_corpus` 359/359.
- The compiler's own cases: checker 1021/1021 (`trait_idx` of `Eq` moved from 5 to 8 with three new built-in traits), codegen 362/362, interp 446/446, lower 150/150.
- `scripts/test.sh fast`: 878 tests, one failure, the skill's concurrency example, which printed `await a + await b` and so depended on which task reached the counter first (the interpreter 5, native workers 4): it prints the counter's total now. `test_doc_blocks`, `test_examples_run`, `test_compiler_parity`: 320/320. Bootstrap: byte-identical fixed point.
- Docs: [[Language/Methods-and-traits#operator-overloading]] (a tested example), [[Language/Expressions-and-operators]], D198 (with a note on D52), [[Development/Testing]], the skill (`SKILL.md`, `reference/builtins.md`, `reference/compiler.md`).
