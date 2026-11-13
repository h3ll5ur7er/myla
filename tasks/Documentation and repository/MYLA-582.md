---
id: MYLA-582
title: What the code read for the skill found stale or doubtful
type: chore
status: backlog
priority: low
labels: [docs, review]
---
Reading the whole compiler and standard library for [[MYLA-581]] (at 706eaec) turned up wiki pages and code comments that no longer match the code, and a few behaviours that look like bugs or gaps. None is fixed yet; each wants a check and either a fix or a decision. The skill's reference files describe the code as it is.

Wiki pages:

- [ ] [[Architecture/Self-hosted-compiler]]: the file table's line counts are from early November (`lower.my` "4,895", now 8,083; `codegen.my` "4,626", now 5,152; …) and it has no rows for `hoist.my`, `ranges.my`, `ir_util.my`, `floatlit_main.my`, `project_main.my`
- [ ] [[Architecture]]: the module table lacks hoist, ranges, ir_util, astcache, stdroot, embedded_std, util, unicode; the diagram has no inline/hoist/ranges/ssa passes and no anf
- [ ] [[Architecture/IR]] "The backend": counts are bumped by `rt __rc_inc`; the code uses `intr rc_inc` (`Intrinsic.RcInc`)
- [ ] [[Language/Targets]]: says integers wrap and shifts are masked "on every target"; since D175 only a plain `myla build` wraps
- [ ] [[Language/Attributes-and-testing]]: says index and missing-key errors "can be expected interpreted only" (they match natively now), and its sample `myla build` output shows `wrote oob`, which the tool doesn't print

Code comments:

- [ ] The headers of `selfhost/codegen.my`, `lexer.my`, `tokens.my` and `ast.my` still say they mirror the retired Python sources
- [ ] `selfhost/interp.my`'s header says "Integer arithmetic wraps" (D175)
- [ ] `lib/std/http.my`'s header says `fetch(url)` is the GET because "the prelude's `get` takes that name"; `pub fun get` exists since MYLA-393
- [ ] `lib/std/task.my`'s channel section says "a notifier lives as long as the program"; D181 lets `close` free it

Tooling lists and tests:

- [ ] `defer` (D135) is missing from `tools/lsp/features.my` `completion_keywords()` and from `vscode-extension/myla/syntaxes/myla.tmLanguage.json`
- [ ] `tests/burn/test_examples_compile.py` still lists `concurrency.my` in `NOT_YET`, though it builds natively and prints what the interpreter prints
- [ ] The builtin names are listed three times, in `checker.my` `is_builtin_func`, `codegen.my` `is_builtin_call_name` and `interp.my` `names_a_builtin`; no test says they agree

Behaviour to decide on (bug or by design):

- [ ] `myla repl` can't declare an `actor` or an `async fun`: `starts_a_declaration` in `selfhost/repl.my` lacks those tokens, so they parse as statements (`parse error: expected an expression, found 'actor'`)
- [ ] An unknown or unimported generic type name is reported as `type 'ListIter' is not generic`, not as unknown or not imported
- [ ] `impl Format for [int]` is accepted, but a list still can't be printed (`has_format` looks only at structs, enums and type parameters)
- [ ] `IoError` is the only error type of the I/O modules without `Eq` (`r == Err(IoError.NotFound)` is a type error), so `HttpError`, `CompressError` and `ArchiveError` compare by message; nothing documents why
- [ ] The prelude's `Hasher { state: 0u64 }` can be built by any program
- [ ] `lexer.my` `scan_fstring` keeps an escaped `{`/`}` (code points 123/125) in a branch that can't run, since `scan_escape` rejects `\{`
- [ ] New hard keywords have no way in: `tokens.keywords()` is pinned to the retired Python lexer's list (`test_grammar.test_the_keyword_list_is_the_lexer_s`), so every new keyword must be soft as `defer` is; a policy for real keywords needs the owner
