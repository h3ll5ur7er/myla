# Clarifications Needed

Open decisions that need your input before (or during) implementation. When you
decide one, it moves to the **Decision log** in [roadmap.md](roadmap.md) and is
removed here.

_Last updated: 2026-06-27 (C1–C7 resolved → D23–D29)._

---

## Still open

**None currently blocking.** The self-hosting scoping questions C1–C7 have been
answered and recorded as decisions **D23–D29** in [roadmap.md](roadmap.md) (see
the "Recently resolved" summary below).

### Likely later batches (not yet detailed)

- v0.2 ADTs/generics: exact `match` pattern syntax (guards, or-patterns, literal
  & binding sub-patterns) and exhaustiveness edge cases.
- v0.3 collections: literal syntax for `[T]`/`[K: V]`/sets, and how mutating
  methods interact with deep immutability (D14) on a `var` binding.
- v0.3 stdlib/modules: package vs. module resolution corner cases, `pub use`
  re-exports, and the `format`/interpolation surface.

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
