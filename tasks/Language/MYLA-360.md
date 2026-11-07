---
id: MYLA-360
title: "myla test: an imported module's cases on built-in-type methods count as the entry's"
type: bug
status: todo
priority: medium
labels: [testing, modules]
---
Found by [[MYLA-320]]. The interpreter's `run_test_cases` and the native harness take a case to be the file's own when its function's name has no module id. A method on a built-in type is named `str.trim` or `int32.double` in every module, so the `#test` cases of an imported user module's `impl str` or `impl [int]` run as the entry file's. MYLA-320 left them out for the implicit std modules by skipping their cases at parsing. A user module still has the problem.

A variant, found by the `std.glob` lane ([[MYLA-326]]): a file under `lib/std/` that imports `std.list` runs `std.list`'s `[str].join` cases as its own, and with `--native` its harness doesn't build ("expected an expression" past the file's end). `std.path` and `std.glob` avoid `std.list` until this is fixed; swap their private helpers for it then.

- [ ] The runners decide a case's file by its declaration's file, not by its name, interpreted and in the native harness
- [ ] A burn test: a program importing a module with `impl str` methods that have cases runs only its own
