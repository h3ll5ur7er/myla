---
id: MYLA-34
title: Remove dead code and bring-up probes from selfhost
type: chore
status: done
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

## Evidence (sign-off, 2026-10-31)

The review ([[Project/Review-2026-10]]) found leftovers: the unused `is_cell` in [[selfhost/lower.my]] (a wrapper of `is_cell_t`), a duplicated comment line before `exit_fn`, and in [[selfhost/codegen.my]] empty section headers from the bring-up (`ownership scopes & drop sites`, `statements`, `enum construction`, `match`, `the ? operator`), one saying "filled in later C4 sub-slices", and the executor's header still saying "D91: one thread" with a first sentence describing the one ring of the one-thread executor. All removed or rewritten (the executor's comment now describes the per-worker rings, MYLA-140). Checked and kept: `all_reports` in [[selfhost/diag.my]] is used by the language server; `load_program_with` in [[selfhost/loader.my]] is the loader's documented API with overrides ([[Architecture/Module-loader]]). The bootstrap reaches its fixed point (6,127,947 bytes, with the other changes of the day) and the codegen gate passes.
