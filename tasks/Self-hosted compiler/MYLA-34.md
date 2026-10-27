---
id: MYLA-34
title: Remove dead code and bring-up probes from selfhost
type: chore
status: review
priority: low
labels: [selfhost, cleanup]
---
- [x] Delete the probe drivers `selfhost/probe_check.my`, `probe_chk.my`, `probe_lex.my`, `probe_parse.my` (nothing references them; done with [[MYLA-28]])
- [x] `eval_owned` → `clone_in_rax` → `is_place` in codegen, and the `__list_clone` runtime only they reach
- [x] `Checker.try_counter`; `MatchVal.has_node` (written, never read); `let di` in `fold_const_expr`; `ret_t = ret_t`
- [x] `str_concat` and the unused `var sb` in `to_string` in `interp.my`
- [x] ~~The unused `fs_line`/`fs_col` parameters in the lexer's f-string hole scanner~~: used since [[MYLA-28]] (the position of "unterminated '{' in f-string")

## How

Removed: `is_place` (the last of the `eval_owned` → `clone_in_rax` chain; the rest and `__list_clone` were already gone) in [[selfhost/codegen.my]]; `Checker.try_counter`, `MatchVal.has_node` and the `ret_t = ret_t` line, a workaround for [[MYLA-59]] that is no longer needed, in [[selfhost/checker.my]]; `str_concat` and the unused `var sb` in `to_string` in [[selfhost/interp.my]]. `let di` in `ensure_const` (formerly `fold_const_expr`) is used, so it stays.

## Evidence

The bootstrap fixed point holds and every self-hosted gate passes (see the commit's suite run).
