---
id: MYLA-191
title: Docs status sweep after the October 2026 review
type: chore
status: todo
priority: medium
labels: [docs]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). The rules on the Language pages are accurate; the status text is one to four months old. One sentence each, verified on 2026-10-31:

- `README.md`: line 26 sends newcomers to the Archive for syntax; 49 "D1–D58"; 93 "notably float codegen"; 98 "once we self-host"; 133 the directive stages omit `module`; nothing about `become`, concurrency, the project tool, the language server, the VS Code extension or `myla check`
- `docs/Home.md`: "four implementations" above three rows; the status paragraph is about the October review, not the IR, concurrency, the project tool or the language server
- `docs/Language.md`: "Concurrency: D89, in progress"; "D1–D58". `docs/Language/Concurrency.md:3`: "in progress"
- `docs/Architecture.md`: the line-count column is 25–40 % low; "Designs not built yet" lists the built project tool and IR. `docs/Architecture/IR.md:3` still opens with the old path. `docs/Architecture/Self-hosted-compiler.md`: four line counts; three pages give three self-compile times (0.8 s, 2.1 s, 2.9 s) and three sizes of the assembly (4.4 MB, 8.0 MB; actual 6.1 MB)
- `docs/Project/Decisions.md:3,5,9`: "made in June 2026", "next number D62", "links point at the Archive"
- `docs/Project/Roadmap.md:50`: "None is designed or scheduled yet" above MYLA-61 (done) and MYLA-62 (eight tasks); 66 still proposes a package manifest; no milestone row for the IR, tail calls or native concurrency
- `docs/Project/Known-issues.md`: "No open issues" for Editor tooling and Documentation while MYLA-153 to 156 are open; remove a line at `done`, not at `review`
- `docs/Getting-started.md:142`: "~410 tests, about 1 s", "burn about 30 seconds" (621 tests, 5 s; burn about 6.5 min). `docs/Development/Testing.md:42,140`: 595 tests; "166 corpus files, 130 type" (203, 167); "65 s / 42 s" vs "400 s"
- `docs/Development/Conventions.md`: five epics listed, eleven exist; "D1–D58". `docs/Development.md`: the layout omits `tools/`, `grammar/`, `scripts/test.sh`
- Every `#Lnn-Lmm` source link on the Language pages points at the wrong code (`Expressions-and-operators.md:3`, `Statements.md:3,80,121`, `Methods-and-traits.md:3`, `Types.md:59`)
- `docs/Language/Structs-enums-and-match.md:29`: fields "separated by commas or newlines" (newlines don't work); `Statements.md:21` "an inner block may shadow" (there is no bare block statement); `Lexical-structure.md:45` vs [[MYLA-180]]
- Enforced but unstated on any Language page: `_` only as a call argument, `Self` only in a trait, `StringBuilder()` takes no arguments, `>>` needs both functions or both integers, `cannot derive 'Ord'`, the `did you mean` help lines
- `examples/maps.my:2` (char keys missing), `examples/strings.my:2` ("arrives in v0.5"); the examples' version-stamped headers; an "examples in reading order" list in Getting started
- `src/myla/__init__.py` `__version__ = "0.0.1"`; `types.py` messages citing "v0.0", "v0.4.1", "v0.4.4"; the Python backend's refusal of concurrency citing [[MYLA-137]] as future

- [ ] Every line above fixed or deliberately kept, and the line-count column dropped or generated
