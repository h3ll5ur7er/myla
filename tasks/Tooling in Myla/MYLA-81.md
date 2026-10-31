---
id: MYLA-81
title: "`myla test` parity in the self-hosted CLI"
type: improvement
status: done
priority: medium
labels: [testing, selfhost]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). [[selfhost/main.my]] already has `test`; make it a drop-in replacement for the Python `myla test`.

- [x] Same output format, summary line and exit status as `myla test` ([[src/myla/cli.py]]), including tests in imported modules ([[MYLA-11]])
- [x] A burn gate that runs every example's and every selfhost module's `#test`s through both and compares the output

## How

- **Names.** The two loaders named modules differently: the Python one by the path from the project root with `..` dropped (`selfhost$tokens` for `../../selfhost/tokens.my`, `src$myla$std$fs` for the standard library), the self-hosted one with one `up` per level climbed and the standard library from its own root (`up$up$selfhost$tokens`, `std$fs`). The Python one changes: `_module_id` follows `selfhost/loader.my`'s rules, which also keep `../x.my` from colliding with `x.my` ([[Architecture/Module-loader]]).
- **Map equality.** The self-hosted interpreter's `value_eq` had no case for maps, so a `#test` expecting a map always failed; maps now compare by entries, in any order, as Python dicts do.
- **The report.** The self-hosted runner collects the lines and prints them after all tests have run (the Python CLI prints after `run_tests` returns, so anything a test prints comes first). A failure says why, as the Python one does: `expected X, got Y` with values as the Python interpreter's `repr` shows them (`py_repr` in `selfhost/interp.my`: `True`, `None`, chars as code points, floats by `std.num.format_float`, strings with Python's quoting, `P { x: 1 }`, `E.B(1)`, `[k: v]`), or `runtime error: <message>`; the runtime error is cleared and the next test runs. `py_repr` replaces the key-only one of the "map key not found" message, and its string quoting now escapes U+00A0 and U+00AD as Python does.
- **`exit` in a test.** The Python runner crashed with a traceback (`_ExitSignal` escaped `run_tests`, and the report was lost); now such a test fails with `exited with status N` in both.

## Evidence

- `tests/burn/test_selfhost_cli.py`, `TestCommandParity`: on all 45 sources with `#test`s (examples, compiler, tools, standard library), stdout and exit status of `myla.py test` and the self-hosted `myla test` are equal. Before: 13 files differed: 9 only in module names (modules above the project root, or the standard library tested from inside it), and in 4 (`tools/lsp/types.my` and the three files importing it) the self-hosted interpreter also failed the three `unify` tests, which compare maps. A program failing in every way (char, bool, strings with both quotes, floats, float32, struct, enum, list, maps, tuple, out-of-range index, Option, uint8, `panic`, `exit`, a test that prints) gives the same report; before, the self-hosted one printed no details and its line order differed.
- `tests/unit/test_loader.py`, `TestModuleIds` (failed before: 5 cases); `tests/unit/test_interpreter.py`, `test_exit_in_a_test_fails_it` (failed with the traceback).
- Full run: 494 unit, 29 integration and 539 burn tests pass; the bootstrap fixed point stays at 7,794,199 bytes.
- Left as is: neither loader resolves symlinks, so a standard-library module reached through a symlinked root is named as a project module (the gate gives both CLIs the same root); a `uint64` above 2^63 would print as negative in the self-hosted report, since its interpreter keeps integers as `int64` without their type.
