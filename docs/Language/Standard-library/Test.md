# std.test

What a test function needs beyond `#test` (D162, [[MYLA-304]], [[Language/Attributes-and-testing#test-functions]]). Every failure is a runtime error, as `assert`'s is: the case fails the way a program fails, and `myla test` is the one place that goes on after one.

| Function | Meaning |
| --- | --- |
| `expect(cond: bool, msg: str = "expectation failed")` | Fails the case with `msg` unless `cond` holds |
| `expect_eq<T: Eq + Format>(got: T, want: T)` | Fails with `expected <want>, got <got>` unless they are equal; `T` is a type `==` compares and `{}` shows: an integer, float, `char`, `bool`, `str`, or a type implementing `Eq` and `Format` |
| `expect_ne<T: Eq + Format>(got: T, other: T)` | Fails with `expected two different values, both are <got>` when they are equal |
| `fail(msg: str)` | Fails the case with `msg` |
| `temp_dir() -> str` | A fresh, empty directory for the running case under `$TMPDIR` (else `/tmp`); each call gives another, and the runner removes them all when the case ends, passed or failed. A runtime error outside a case (`myla run`) |
| `program() -> str` | The path of the project's program, which `myla test` builds before the files of `tests/` run ([[MYLA-306]]); a runtime error elsewhere |

The printable primitives count as implementing `Format` for a bound (`expect_eq(3, 4)`); a value `==` doesn't compare (an `Option`, a `Result`, a list) is checked with `expect` on a `match`, or taken apart with `?` in a test function returning `Result<(), E>`. The module's other public functions (`Case`, `case_index`, `child_done`, `run_in_children`, `report_inline`, `summary`, `end`, `case_detail`, `repr_str`, `without_module_ids`) are the runner of the harness `myla test --native` builds ([[Language/Attributes-and-testing#native-runs]]), not for programs.
