---
id: MYLA-187
title: "myla test file.my runs the #test cases of imported std modules"
type: bug
status: review
priority: medium
labels: [cli, tests, stdlib]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). A file with one `#test` that imports `std.json` prints 53 lines under `python3 myla.py test` and `build/myla test`: its own case and 52 of the library's (`std$num$format_float #10` and the rest). [[src/myla/std/fs.my]] avoids `#test` for exactly this reason, while `json.my` and `num.my` carry 51 cases, so the policy is inconsistent and the user sees the library's tests. Project mode (`myla test` in a project) already runs only each file's own cases.

- [x] File mode runs the entry file's cases only, in both CLIs (the parity test of [[MYLA-81]] pins it); the std modules' own cases keep running through `tests/burn/test_json.py`
- [ ] `fs.my`, `io.my`, `process.my`, `toml.my` and `task.my` may then carry `#test` cases too

## Evidence

- Both CLIs run only the entry file's cases (`run_tests(own_only=True)`; the self-hosted `run_test_cases` lost its now constant flag): `myla test` of a file importing `std.json` prints its own case, not 52 lines of the std modules'. `test_packages.test_test` now checks that the packages' cases are left out; the command parity test passes; the std modules' own cases still run through `tests/burn/test_json.py` (`myla test` of each).
- The second item (std modules carrying `#test` cases) is now possible; none added.
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
