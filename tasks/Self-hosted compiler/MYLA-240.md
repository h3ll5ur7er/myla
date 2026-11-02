---
id: MYLA-240
title: "Recorded answers survive the migration to builtin methods"
type: improvement
status: review
priority: medium
labels: [tests, golden, migration]
---
The owner's decision (2026-11-02): before the examples, docs and test programs move from `push(xs, v)` to `xs.push(v)` ([[MYLA-221]] step 3), the retired Python toolchain's recorded answers ([[Development/Testing]], "Recorded answers") must keep answering for the rewritten programs, instead of being lost because they are keyed by the program's text.

- [x] The rewriting tool in the repository (`scripts/to_methods.py`): Myla files, programs in the tests' Python strings, programs in the tests' JSON data
- [x] A trace of every question the burn suite asks the recordings, before the rewrite
- [x] Aliases: the key of a question about a rewritten program leads to the recorded answer of the original, with positions moved to the rewritten text (columns on rewritten lines; lines never move)
- [x] The gates that compare tokens and syntax trees keep comparing the texts as recorded (their syntax stays valid)
- [x] The rewrite done, the burn suite passing with the oracle coverage it had (skips counted before and after)

## Evidence

- **The tool.** `scripts/to_methods.py` rewrites `f(a, rest)` to `a.f(rest)` for the ten builtins that are methods. It works on Myla files, on the `myla` blocks of Markdown, on the Myla programs in the tests' Python string literals (only literals that look like Myla; the edit is checked with `literal_eval`), and on the tests' JSON data. It works from the self-hosted lexer's tokens, so strings and comments stay as they are, and it moves no line: the newlines of a multi-line call move inside the receiver's parentheses. `rewrite_mapped` also says where each character went.
- **The trace.** `MYLA_GOLDEN_TRACE=file` appends each question to the file: the oracle, the key, whether it has an answer, and the arguments with the texts of the files they name. Before the rewrite, the burn suite got 4,745 distinct recorded answers from 26 oracles.
- **The aliases.** `tests/burn/golden_aliases.py` checks that every traced key reproduces from the traced texts (all did). It then rewrites each text and stores, under the new key, the old key and each changed line with each old column's new place: 828 aliases in 19 files, 135 KB, in `tests/burn/data/golden/aliases/`. `_golden.py` answers an unknown key from its alias and moves the columns in the answer: rendered `--> file:L:C`, the source line and its caret, canonical `err L C SL:SC-EL:EC` lines, `file.my:L:C`, the checker's `column`/`underlined`, the language server's member positions, and the runtime-error tuples. Rebuilding from the same trace gives byte-identical files.
- **The structural gates.** The lexer's tokens and the parser's tree are the program's own structure, so they get no aliases (`STRUCTURAL` in the builder). Their gates read copies of the 30 rewritten examples as they were recorded, from `tests/burn/data/recorded_corpus/<path>` (`recorded()` in `_golden.py`), keyed by their original paths.
  - On the way: the corpus loops raised `SkipTest` at the first changed `lib/std/` file, which ended the loop. The examples used to sort before it; the copies sort after. Each file is now its own subtest, so a changed file skips only itself.
- **The rewrite.** 59 files changed, about 560 calls: the examples and the error corpus, the language pages and the README, the programs in the burn tests and their JSON data, and the VS Code extension's test fixture.
  - Kept in the function form: programs about it. These are three checker snippets and two entries of `type_error_snippets.json` about the function's errors, `type_pop_non_list.my` and `type_sb_build_non_builder.my`, the parity case of a local closure shadowing a builtin, and the "function forms still work" lines.
  - The checker's D95 walk (re-entrancy writes) and its effect analysis now count the method forms of the mutating builtins as writes (`mutating_builtin`). The rewritten `warn_reentrancy_push_and_loop` found that. `test_a_mutating_method_changes_an_actor_field` (`test_builtin_methods.py`) pins it: a direct `push`, a `pop`, and a `push` in a synchronous method of the actor. All three fail with the compiler before the change and pass after. A change inside a `let` initializer goes unseen in both forms; that gap predates this task.
  - Two pinned trap positions in `test_native_runtime.py` moved with their rewritten lines.
- **Coverage.** A trace after the rewrite, compared per oracle with aliases resolved: 4,745 answers before and 4,745 after, none lost in any oracle.
  - The burn suite passes. Skips went from 41 to 111 only because each changed `selfhost/` and `lib/std/` file in the two corpus gates is now one skipped subtest; before, one skip covered the rest of the loop.
- **Docs.** [[Development/Testing]], "Rewriting the recorded programs", has how to rewrite again.
