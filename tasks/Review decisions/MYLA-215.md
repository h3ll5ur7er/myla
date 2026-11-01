---
id: MYLA-215
title: "Decision: the language ergonomics round"
type: chore
status: review
priority: medium
labels: [decision, language, ergonomics]
---
From the October 2026 review ([[Project/Review-2026-10]], §13.9): small language changes that would make everyday code shorter, each a decision of its own. Most are sugar the front end can desugar, which costs the two parsers, the two checkers, [[grammar/myla.ebnf]] and the tree-sitter grammar, not the interpreters and backends.

## Sub-questions, options and recommendations

- **`float` = float64**: [[MYLA-203]].
- **Methods on builtin collections**: [[MYLA-204]].
- **Map iteration order**: [[MYLA-179]].
- **`if` as an expression.** Options: no; `let x = if c { a } else { b }` where each branch block ends in an expression and `else` is required; a ternary operator. *Recommended:* the block form, no ternary; `match` is already an expression.
- **Compound assignment.** Options: none (today, [[Language/Statements]] says "not yet"); `+=`, `-=`, `*=`, `/=`, `%=` and the bitwise ones as `x = x op y` with the place evaluated once. *Recommended:* add them; the most-missed feature in practice.
- **Line continuation.** Options: none; inside brackets only; inside brackets and after a trailing binary operator. *Recommended:* inside `()`, `[]` and `{}` of expressions, and after a binary operator that ends a line (a leading operator still starts a new statement).
- **Trailing commas.** *Recommended:* one rule, allowed after the last element of every comma-separated list.
- **`if let` / `while let`.** *Recommended:* yes, as sugar over `match`.
- **Real trait-method bounds** (check a generic body against its bounds once, instead of only after monomorphization). The largest item; *recommended:* later, on its own, when generic code in the standard library needs it.

## Decision

**D104 (2026-11-01): the recommendations**, and insertion order for maps (D105, [[MYLA-179]]). Implementation: [[MYLA-222]] (`if` expression), [[MYLA-223]] (compound assignment), [[MYLA-224]] (line continuation), [[MYLA-225]] (trailing commas), [[MYLA-226]] (`if let`/`while let`), [[MYLA-227]] (trait bounds, later); floats [[MYLA-220]], methods [[MYLA-221]].

- [x] Decided, and recorded on [[Project/Decisions]]
- [x] The implementation tasks created or updated to match
