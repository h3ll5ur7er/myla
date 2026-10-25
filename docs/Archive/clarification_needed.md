# Clarifications Needed

Open decisions that need your input before (or during) implementation. When you
decide one, it moves to the **Decision log** in [roadmap.md](roadmap.md) and is
removed here.

_Last updated: 2026-06-28 (V1–V8 → D30–D37 (v0.2 locked); W1–W6 → D38–D43 (v0.3 locked); X1–X9 → D45–D53 (v0.4 abstraction locked); **v0.5 scope: D54–D58 locked, full design in [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md)**)._

---

## Still open

**None currently blocking.** v0.2 (V1–V8 → **D30–D37**), v0.3 collections/strings/
ops (W1–W6 → **D38–D43**), and v0.4 abstraction (X1–X9 → **D45–D53**) are all
answered and recorded in [roadmap.md](roadmap.md); the full v0.4 design is locked
in [v0.4-abstraction.md](v0.4-abstraction.md).

### v0.5 scope (locked, not yet implemented)

- The full v0.5 design is now in
  [v0.5-modules-and-runtime.md](v0.5-modules-and-runtime.md): modules + imports +
  `pub` re-exports + resolution rules (D17/D22/D54/D57), the `std` skeleton,
  floats (D19/D56), the `char` type + UTF-8 string model (D25), the freestanding
  I/O runtime (D29), restricted generic traits (D55), and string interpolation
  (D58).

### Later batches (not yet detailed)

- v0.5 stdlib: the exact module surface grows on demand during self-hosting;
  format/interpolation **specs** (`{x:04}`) are a later, joint feature.
- Deferred within v0.3: **sets** (revisit when a concrete need appears, D39).
- Deferred to post-self-hosted-codegen: process spawning (`fork`/`execve` to
  drive `as`/`ld`) and a package **manifest** format (D29; §1.4).

---

## Recently resolved (now in roadmap.md decision log)

Q1 drop `++`/`--` (D9) · Q2 attributes into v0.0 (D10) · Q3 default `int` literal
+ type suffixes (D11) · Q4 reference counting (D12) · Q5 monomorphization (D13) ·
Q6 deep immutability (D14) · Q7 by-value capture, `ref` planned (D15) · Q8
`Result` + `?` (D16) · Q9 explicit Python-like imports (D17) · Q10 custom
operators postponed; trait overloading first (D18) · Q11 `float32`/`float64` +
`float` alias + suffixes (D19) · Q12/Q13 full `intN`/`uintN`, `iN`/`uN` suffixes
(D20) · P1 length-prefixed immutable `str` in v0.0, builder/views/format later
(D21) · O1 import resolution rules: dot-relative bases, full-path binding +
`as`, `pub`, collisions are errors (D22).

**Self-hosting scoping:** C1 milestone renumbering — self-hosting is the v1.0
destination (D23) · C2 `>>` does both shift & compose, resolved by operand type
(D24) · C3 dedicated `char` type for UTF-8 (D25) · C4 `x as T` casts + wrap/extend
semantics (D26) · C5 `var self` mutating receiver (D27) · C6 module-level `const`
only (D28) · C7 freestanding no-libc syscall runtime, defer `exec` (D29).

**v0.2 data modeling:** V1 `match` is an expression (D30) · V2 `Enum.Variant`
construction + prelude shorthand (D31) · V3 positional payloads only (D32) · V4
pattern set incl. or-patterns + guards (D33) · V5 generic args inferred at call
sites (D34) · V6 arity ≥ 1 with `(x,)` 1-tuples, no unit type (D35) · V7
same-carrier `?` (D36) · V8 `==` primitives-only, structural eq via traits later
(D37).

**v0.4 abstraction:** X1 no orphan rule / impls freely mixed (D45) · X2 no UFCS,
per-type method namespace (D46) · X3 `self`/`var self` needs mutable lvalue
receiver (D47) · X4 by-value capture, `ref` later (D48) · X5 16-byte
`(code_ptr, env_ptr)` fat value + refcounted env (D49) · X6 `|>` + `>>`
compose-by-type (D50) · X7 `_` partial app, no currying (D51) · X8 fixed
operator-trait set + `#derive(Eq)` (D52) · X9 limited built-in-trait bounds (D53).

**v0.5 scope:** re-exports via a `pub`-prefixed import, `as` required on
`pub import` (D54) · restricted generic traits, ≤1 impl per type, no overload
resolution (D55) · floats scheduled into v0.5 per D19/D20 (D56) · package/module
resolution corner cases — files=modules/dirs=packages, `foo/foo.my` package
root, collisions error, entry-dir root, shadow-protected builtins,
module-before-item, cycles ok (D57) · string interpolation `f"…{expr}…"` as sugar
over `format` (D58).
