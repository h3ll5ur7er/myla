---
id: MYLA-187
title: "myla test file.my runs the #test cases of imported std modules"
type: bug
status: todo
priority: medium
labels: [cli, tests, stdlib]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). A file with one `#test` that imports `std.json` prints 53 lines under `python3 myla.py test` and `build/myla test`: its own case and 52 of the library's (`std$num$format_float #10` and the rest). [[src/myla/std/fs.my]] avoids `#test` for exactly this reason, while `json.my` and `num.my` carry 51 cases, so the policy is inconsistent and the user sees the library's tests. Project mode (`myla test` in a project) already runs only each file's own cases.

- [ ] File mode runs the entry file's cases only, in both CLIs (the parity test of [[MYLA-81]] pins it); the std modules' own cases keep running through `tests/burn/test_json.py`
- [ ] `fs.my`, `io.my`, `process.my`, `toml.my` and `task.my` may then carry `#test` cases too
