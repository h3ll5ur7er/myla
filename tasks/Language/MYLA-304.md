---
id: MYLA-304
title: "Test functions, failures that unwind, std.test and selection (step 1 of MYLA-303)"
type: feature
status: in-progress
priority: high
labels: [testing, language, interpreter, std]
---
Step 1 of [[MYLA-303]], decided as D162: the interpreter's half of the test system.

- [ ] A bare `#test` on a function without parameters is a test function (sugar for `#test()[()]`): a result of none or `Result<(), E>`; reported as `PASS  name`, an `Err(e)` as `FAIL  name: e` with `e` rendered as `{}` shows it
- [ ] `[panic("message")]` and `[exit(n)]` as expected values: the case passes when the call ends in that runtime error (the message exact) or that exit status
- [ ] A failed case unwinds its deferred blocks, innermost first (D141 amended); a deferred block that fails is reported with the case
- [ ] `std.test`: `expect`, `expect_eq`, `expect_ne`, `fail`, `temp_dir` (a fresh directory per call, removed when the case ends however it ends), `program` (step 3's)
- [ ] `myla test --only <text>` and `--list`, in file and project mode
- [ ] A case's standard output shown only when it fails, under the FAIL line
- [ ] The error corpus, burn tests, the Language page, Testing, the skill
