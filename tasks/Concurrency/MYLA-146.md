---
id: MYLA-146
title: A diagnostic for actor state changed across an await
type: feature
status: done
priority: medium
labels: [concurrency, checker, selfhost, language]
---
From the concurrency stress tests ([[MYLA-144]], test 6, "reentrancy across an await"), the user's decision: keep reentrant actors (D89 (2)) and add a compiler diagnostic. An actor method that reads a field before an `await` and writes it after, without reading it again, acts on a value another call may have changed meanwhile: `if self.stock == 0 { … }; await pay.charge(); self.stock = self.stock - 1` sold the last item twice (stock -1, every time on one worker).

- [x] The rule and how it is silenced (a decision, D95): the user chose warnings, new in both checkers; the warning goes away when the field is checked again after the `await` or changed before it
- [x] Both checkers, the same diagnostic; both CLIs, `check --canonical`, the language server; the stress test's idioms accepted

## Design (D95)

- **Warnings.** The Python checker collects `CheckWarning`s (`kind` "warning") in `Checker.warnings`, the self-hosted one `CheckErr`s in `Checker.warnings`, each sorted by place. The CLIs print them, each in its file, before running or building (`cli._warn`; `driver.load_and_check` with `loader.warning_reports`); `check --canonical` and `check_main` print `warn <line> <col> <span> warning: <message>` and the notes before `ok` (`canon.canonical_warning`); the language server publishes them with severity 2.
- **The rule** (`_Reentrancy` in `types.py`, `Reentrancy` in `checker.my`, the same walk): per field, the epoch of its last examination by a condition (directly, or through a local whose initializer read it, at that local's epoch); per local, the fields its value was read from and when. A change to a field in a later epoch than its examination warns ("was checked before an 'await' and is changed after it"), as does one set from a local read in an earlier epoch ("is set from a value read before an 'await'"); a change settles the field's examination. The note points at the `await` that started the next epoch, the help says what to do.

## Evidence

- Test 6 of the plan (`if self.stock == 0 { return false }; let paid = await p.charge(); self.stock = self.stock - 1`): `warning: 'self.stock' was checked before an 'await' and is changed after it: another call to this actor may have changed it meanwhile`, a note at the `await`, `help: check it again after the 'await', or change it before`, from both checkers and both CLIs alike (`test_warnings_are_printed_and_the_program_runs`), and from the language server at severity 2 (`test_warnings_have_their_severity`); the program still runs.
- `WARNINGS` in `tests/burn/test_selfhost_checker.py`: a stale check, a stale value, a `push` after a check, a `while` loop, a `match` with a lambda; quiet for checking again after the `await` and for reserving before it. Both checkers print the same lines. No example, standard library module or part of the compiler gets a warning.
- `t06_recheck_after_the_await` (the stress test with the second check): `successes 1 stock 0` everywhere.
- Unit 621, integration 2, burn 808 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (6,107,397 bytes).
