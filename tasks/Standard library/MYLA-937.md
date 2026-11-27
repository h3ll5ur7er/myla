---
id: MYLA-937
title: "On Windows remove_file and remove_dir_all can't remove a read-only file: `myla clean --deps` fails on a Git checkout"
type: bug
status: review
priority: high
labels: [stdlib, fs, project, windows]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group B). On the native Windows runner (run 277) test_project_fetch's `shutil.rmtree` of an app's `.myla/` fails with access denied on `.myla\deps\greet-…\.git\objects\pack\pack-….idx`: Git makes its object files read-only, and Windows' `DeleteFileW` refuses a read-only file (Linux's unlink doesn't look at the file's permissions). std.platform's Windows `remove_file` ([[lib/std/platform_windows.my]]) called `DeleteFileW` alone, so std.fs's `remove_file` and `remove_dir_all` failed the same way, and with them `myla clean --deps` (`selfhost/project_cmd.my`) and `check_out`'s removal of an interrupted `.partial` clone (`selfhost/fetch.my`), both of which hold Git checkouts. Reproduced under Wine: `remove_dir_all` of a tree with a `chmod 444` file printed `failed` and left it.

- [x] Windows' `remove_file`: a delete that is access denied on a read-only file (not a directory) clears the attribute (`SetFileAttributesW`, kernel32, so the seed needs nothing: the import is recorded where it is used) and deletes again; the attributes are put back if that fails too, as Go's `os.Remove` and Rust's `remove_dir_all` remove one. `writable_attributes`'s `#test`s
- [x] test_project_fetch's own `rmtree` of `.myla/` makes the read-only files writable on Windows (`_remove_tree`); the test goes on to `myla clean --deps`, which now removes the checkout itself
- [x] Evidence: under Wine `remove_dir_all` of that tree prints `removed` and `gone`, and `myla test lib/std/platform_windows.my --target x86_64-windows` passes 204/204; on Linux `build/myla test lib/std/platform_windows.my` 204/204, the bootstrap's fixed point, test_project_fetch 9, check-seed.sh
- [ ] test_project_fetch on the `burn-windows` job
