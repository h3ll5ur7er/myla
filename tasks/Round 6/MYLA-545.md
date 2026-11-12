---
id: MYLA-545
title: "R3 Lexer, parser, loader: a swallowed declaration, D186's messages, the look-ahead budget, a root written with `..`"
type: bug
status: todo
priority: medium
labels: [lexer, parser, loader, round-6]
---
Work package R3 of [[Project/Review-2026-11-12]]. Files: `selfhost/lexer.my`, `selfhost/parser.my`, `selfhost/loader.my`. Same lane as [[MYLA-413]] (reopened); [[MYLA-552]] touches the loader after it.

- [ ] **Residual Z1**: after a missing `}` and one extra `}`, a swallowed declaration that doesn't start its line (`/* c */ fun`, `}; fun`, `#test(1)[3] fun`, `#derive(Eq) pub struct`) still loads with no error when the library is read lazily; `myla check` of the module itself catches it (`repro-r5/parser/mk.sh`, `a.txt`, `b.txt`, `c.txt`)
- [ ] `starts_decl`: 8 of its 12 declaration keywords have no test (mutants survive)
- [ ] **D186's refused forms** get a message about something else: `both(a < p.x, c > (d))` is `module error: unknown module 'p' in the type 'p.x'` (`e1.my` to `e3.my`, `t1.my`). Say what was tried and how to write the comparison
- [ ] The 128-token look-ahead budget is a silent cliff: the same call parses with 63 tokens between the brackets and not with 64 (`budget_63.my`, `budget_64.my`, `deep_43.my`). A message that names the budget, or no budget
- [ ] A chain of about 16,000 binary operands overflows the compiler's stack (`and_16000.my`)
- [ ] `v.0.0` on a tuple of tuples is lexed as a float; `(v.0).0` works
- [ ] **`in_stdlib` with `..`** ([[MYLA-397]]): from `lib/std`, `myla test option.my --stdlib ..` gives `duplicate method 'map'`, and `platform_aarch64.my --stdlib .. --target aarch64-linux` gives `'__addr_of' reads or writes raw memory`; `../myla/lib/std/x.my --stdlib lib` fails the same way. Make both paths absolute before comparing; add the spellings to the burn test (`repro-r5/harness/dotdot.sh`)
