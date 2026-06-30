# Archived design docs

These documents were the **working design notes used while building Myla** up to
the self-hosting fixpoint (v1.0). They are kept for historical reference but are
no longer the living source of truth — they describe features *as they were being
designed*, not necessarily the final shipped behavior.

For current information see:

- [../roadmap.md](../roadmap.md) — live status + the locked decision log (D1–D58)
- [../language-spec.md](../language-spec.md) — the language reference
- [../grammar.md](../grammar.md) — the formal grammar
- [../architecture.md](../architecture.md) — toolchain architecture
- [../known_issues.md](../known_issues.md) — known limitations of the self-hosted compiler

## Contents

| File | What it was |
|------|-------------|
| `self-hosting.md` | The plan for reaching self-hosting (gap analysis, tiers, milestone ordering). The fixpoint described in §5 has been reached. |
| `future-features.md` | Catalog of post-v0.0 feature design sketches. Almost all are now implemented; the decisions are recorded in `roadmap.md`. |
| `clarification_needed.md` | Tracker for open design questions during development (all resolved into the decision log). |
| `v0.2-data-modeling.md` | Detailed design for enums/`match`, tuples, generics, `Option`/`Result`. |
| `v0.3-collections-and-ops.md` | Detailed design for lists/maps, the string toolkit, bitwise/casts, `const`, etc. |
| `v0.4-abstraction.md` | Detailed design for methods/`impl`, lambdas/closures, pipelines, traits. |
| `v0.5-modules-and-runtime.md` | Detailed design for modules/imports, floats, `char`/UTF-8, the freestanding I/O runtime. |
