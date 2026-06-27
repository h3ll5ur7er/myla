# Clarifications Needed

Open decisions that need your input before (or during) implementation. When you
decide one, it moves to the **Decision log** in [roadmap.md](roadmap.md) and is
removed here.

_Last updated: 2026-06-27._

---

## Still open

**None currently blocking.** All outstanding design questions (Q1-Q14, plus the
import-resolution and string-scope follow-ups) have been answered and recorded as
decisions **D9-D22** in [roadmap.md](roadmap.md).

New questions will be added here as they arise. The most likely next batch will
come when implementation starts:

- v0.0.1 scaffolding: concrete Python package/test layout details.
- v0.2 ADTs/generics: exact `match` pattern syntax and exhaustiveness edge cases.
- v0.3 stdlib/modules: fine details of package resolution, `pub use` re-exports,
  and the `format`/interpolation surface — to be settled when that work begins.

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
