---
id: MYLA-940
title: "run.mjs gives a wasm program Windows' working directory: its relative paths aren't found under Node on Windows"
type: bug
status: todo
priority: medium
labels: [wasm, windows, testing]
---
Found by [[MYLA-926]] step 2's port of the burn suites (2026-11-24, group D, run 277): on the `burn-windows` job `test_wasm.WasmParity.test_files` fails every file operation the program makes (`mkdir failed`, `write failed`, … `rmdir failed`), where the x86-64 build of the same program, run in the same directory, gives `written\n8\ntrue\n…`.

`tools/wasm/run.mjs` gives the program `PWD` as `process.cwd()`, which on Windows is `C:\Users\…\Temp\tmpX`. `wasi_path` in `lib/std/platform_wasm.my` joins a relative path to it (`C:\Users\…\tmpX/wd`: no leading `/`, so nothing is stripped), and the shim's `joinPath` puts that under the preopened `/`: `/C:\Users\…\tmpX/wd`, which Node on Windows reads from the root of its working directory's drive, `C:\C:\Users\…` (a `:` in a name: no such file).

An absolute Windows path given to such a program (`D:\a\myla\myla\examples\maps.my`) is a relative name to WASI the same way. The tests now give the program a path as it can name it (`tests/burn/test_wasm.py`'s `under_the_runner`: the path on its drive, without the drive and with `/`, `/a/myla/myla/examples/maps.my`, Node run on that drive), which is how Node reads a `/` path on Windows. That fixed `test_compiler`, `test_the_compiler_compiles_itself` and test_selfhost_parser's `test_the_wasm32_tools_hold_a_long_chain`; `test_files` can't be fixed in the test, as its relative paths go through the runner's `PWD`.

The fix is in the runner (`tools/wasm/`, the website's area, so not made by the port): on Windows, `PWD` in the same spelling, the working directory on its drive without the drive and with `/` (`process.cwd().replace(/^[A-Za-z]:/, "").replaceAll("\\", "/")`; a share's `\\srv\share\…` has no such spelling, and needs a decision if it matters), and run.mjs's comment saying that on Windows the program's `/` is the root of the working directory's drive.

- [ ] run.mjs: `PWD` on Windows as above (Linux's unchanged)
- [ ] Evidence: `test_wasm.WasmParity.test_files` passes on the `burn-windows` job; test_wasm passes on Linux as before
