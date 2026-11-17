---
id: MYLA-793
title: "R7-4 Parser and loader: #test text in a body (M9), long chains (M10), lazy positions, path identity, a guard on the check's cost"
type: bug
status: todo
priority: medium
labels: [parser, loader, round-7]
---
Work package of [[Project/Review-2026-11-17]], lane "Parser and loader" (section 5). Files: `selfhost/parser.my`, `selfhost/loader.my`. The reproducers are in the review's bundle (`repro-r6/`, with a README per area); each fix turns its reproducer into a test that fails before it. The owner's decision it builds: D258 (the guard). New tasks it files take ids 825–832.

- [ ] **M9** (old): text that starts `#test` inside a function body of an imported module is skipped unparsed: `myla check` says `ok`, statements inside `#test(…)[ … ]` vanish (against D179). `repro-r6/loader/attr_in_body/`. File a task
- [ ] **M10** (old): 6,000 `|> id` or 20,000 `else if` arms overflow the compiler's stack: the chain limit doesn't count them. `repro-r6/loader/pipe_chain_6000.my`. [[MYLA-545]]'s follow-up
- [ ] [[MYLA-413]]/[[MYLA-545]]'s follow-ups: a lazily read body's missing brace reported at another place than eagerly (116 of 3,000 mutants); D186's note on a plain type error
- [ ] Path identity: a library root reached through a symlink gives 18 duplicate-method errors; a program's own `std/rt.my` checks and runs but every build fails with `module id collision`
- [ ] Decision 4's guard: a test that pins `myla check`'s and `myla run`'s instruction counts for a hello world (with headroom), so the next implicit module shows up red ([[MYLA-552]]/[[MYLA-608]]'s follow-up)
- [ ] [[MYLA-710]]'s follow-up: one unparsable std body drops the whole module's hover and completion; float literals and `Index` results untyped in the language server
