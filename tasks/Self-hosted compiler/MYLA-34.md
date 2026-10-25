---
id: MYLA-34
title: Remove dead code and bring-up probes from selfhost
type: chore
status: backlog
priority: low
labels: [selfhost, cleanup]
---
- [ ] Delete the probe drivers `selfhost/probe_check.my`, `probe_chk.my`, `probe_lex.my`, `probe_parse.my` (nothing references them)
- [ ] `eval_owned` → `clone_in_rax` → `is_place` in codegen, and the `__list_clone` runtime only they reach
- [ ] `Checker.try_counter`; `MatchVal.has_node` (written, never read); `let di` in `fold_const_expr`; `ret_t = ret_t`
- [ ] `str_concat` and the unused `var sb` in `to_string` in `interp.my`
- [ ] The unused `fs_line`/`fs_col` parameters in the lexer's f-string hole scanner
