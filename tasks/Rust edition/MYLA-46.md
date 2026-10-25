---
id: MYLA-46
title: Rust docs disagree with the parser
type: bug
status: backlog
priority: low
labels: [rust, docs, parser]
---
- [ ] language-spec §4 says a newline inside `( … )` never ends a statement, but `(1\n + 2)` is a parse error: the parser skips newlines only at specific points
- [ ] Parentheses don't re-enable struct literals: `if (p == P { x: 1 })` fails because `parse_paren_or_lambda` doesn't reset `no_struct_lit`
- [ ] The `select` example in `docs/concurrency.md` (trailing comma, expression arm body) doesn't parse; the parser wants block bodies
- [ ] sema's "unknown attributes / duplicate definitions" only holds for functions (and structs for duplicates)
