---
id: MYLA-936
title: "`myla test` doesn't see a test program of `tests/` whose lines end in CRLF: `// output:` is read as `output:\r`"
type: bug
status: review
priority: high
labels: [project, testing, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group B): on the native Windows runner (run 277) test_project_commands' four `TestTestsDirectory` tests miss the whole `== tests/` block, and the total counts fewer files (`4/5 passed in 3 files.` for `7/9 passed in 7 files.`). The test writes its files in text mode, so on Windows their lines end in CRLF, as they do in a Windows checkout with Git's `core.autocrlf`. `selfhost/test_programs.my`'s `trailing_block` split the source at `\n` only, so each line of the trailing block kept its `\r`: `// output:\r` isn't `output:`, `test_program_of` found no test program, and `project_test` ([[selfhost/project_cmd.my]]) took each one for a file of `#test` cases, which has none to show. The `FAIL  fails_on_purpose: … got hello Mr Bob\n` line in the same output is expected (`GREETER_WANT`: the test fails on purpose). The test files' paths and the `tests/` prefix were right (`== tests/cli.my` showed).

- [x] `trailing_block` takes a line's `\r` before its `\n` off (`without_cr`), so the sections, the input, the output and the stderr of a CRLF test program are what an LF one's are; `#test` cases of a CRLF block for `trailing_block` and `test_program_of` (they failed first: `['output:\r', 'hi\r']`, `None`)
- [x] Evidence on Linux: `build/myla test selfhost/test_programs.my` 34/34 (29/31 before the fix), the bootstrap's fixed point, test_project_commands 20, test_project_fetch 9, test_std_cache 3, check-seed.sh. Under Wine, CRLF `boom.my` and `exits.my` built for x86_64-windows end with 1 and 3 and print LF, as the expectations say; `myla test selfhost/test_programs.my --target x86_64-windows` 34/34
- [ ] test_project_commands on the `burn-windows` job
