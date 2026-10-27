---
id: MYLA-99
title: Debug adapter in the VS Code extension
type: feature
status: review
priority: medium
labels: [vscode, debugging]
---
Debug Myla programs in VS Code: `F5` on a `.my` file builds it with `myla build -g` ([[MYLA-66]], [[MYLA-71]]) and debugs it with gdb, with nothing but this extension and gdb installed. The open item "an editor front end" of [[MYLA-66]].

- [x] A `myla` debug type with a `launch` configuration: `program` (a `.my` file, a binary built with `-g`, or a project), `args`, `cwd`, `env`, `stdin`, `stopOnEntry`, `gdbPath`, `trace`
- [x] `F5` without a `launch.json` debugs the active file; a build error stops the launch with the compiler's message and a jump to it
- [x] Line breakpoints verified at the line gdb chose, conditions, hit counts, function breakpoints
- [x] Continue, next, step in, step out, pause; the stack with Myla names and positions
- [x] Locals and arguments; structs, tuples, enums, lists expand; heap strings and lists inside aggregates shown as values; `setVariable`
- [x] Evaluate in the Debug Console and on hover; `-exec <gdb command>`
- [x] Runtime errors stop as exceptions with their message and position; program output in the Debug Console; the exit code; Run Without Debugging
- [x] Unit tests (MI, DAP, presentation, the session against a fake gdb) and an integration test against real gdb, built by both CLIs
- [x] A hook for projects: `debugTarget` debugs a project's `src/main.my` until project-mode `myla build` exists ([[MYLA-94]])

## How

The decision is D78 ([[Project/Decisions]]); the architecture is on [[Architecture/Editor-tooling]].

- **An own adapter over GDB/MI.** `src/debug/session.ts` (`MylaDebugSession`) speaks the Debug Adapter Protocol to the client and drives `gdb --interpreter=mi3` through `src/debug/gdb.ts` (one command in flight, tokens, console output collected per command) and the parser in `src/debug/mi.ts`. It needs nothing from VS Code: the extension runs it in the extension host (`DebugAdapterInlineImplementation` in `src/debugProvider.ts`), `src/debug/adapterMain.ts` runs it on stdio (`node out/debugAdapter.js`) with the Content-Length framing of `src/debug/dap.ts`. cpptools or CodeLLDB would do the gdb side, but neither knows Myla's names, runtime errors or cell layouts, and either is a large dependency users must install.
- **Building.** The configuration provider builds the program with `-g` into the extension's storage (`debugOutputPath`: the file's name and a hash of its path) with the CLI of `myla.cliPath` (`build/myla`, else `python3 myla.py`), saving dirty `.my` editors first, and passes the binary as `executable`; the adapter builds on its own only when no `executable` is given (other clients, the tests). Absolute source paths make the binary's file names absolute, so breakpoints use the full path; a binary built from a relative path falls back to the base name.
- **Program output.** gdb runs the program through `/bin/sh`, so `set args` ends in `< stdin > out 2> err` with files in a temporary directory; the adapter reads what is new every 100 ms while the program runs and at every stop and at the exit, so nothing is lost or reordered against the stop. A pipe of its own would need a pty, which Node can't make without a native module.
- **Runtime errors.** The `Runtime errors` exception filter (on by default) is a breakpoint on `*__panic`; at the stop the adapter reads the message from `%rdi` (`[len][bytes]`) and the position record from `%rsi` (D75) and reports an `exception` stop; the `__panic` frame has no source and is `subtle`, so VS Code shows the Myla frame that failed.
- **Values.** Scopes come from `-stack-list-variables` (types from `--simple-values`, the values gdb prints from `--all-values`); children from variable objects, created when a value is first expanded. `src/debug/present.ts` decides what expands, hides an enum's `<tag>` and shows the active variant's fields, shows a list cell's items, and builds each child's expression in gdb's Rust syntax (`s.0`, `xs[2]`, `(*bag.items).items[0]`) for `evaluateName` and for a value gdb's variable object only summarizes (`{...}`). A heap string inside an aggregate is read from memory and shown as text, a list cell as its items: what D75 left as pointers shows as values in the Variables view.
- **Order.** Requests are handled one after the other (so a `configurationDone` can't overtake breakpoints being set), except `pause`, `terminate` and `disconnect`; `*stopped` records queue behind them. A step that ends in `_start` (stepping off the end of `main`) continues to the exit.

## Evidence

- `npm test` in `vscode-extension/myla`: 51 tests pass, among them `test/integration/adapter.test.ts` (6 sessions against gdb 15.1: breakpoints moved to the next line with code, replaced per file; the stack; locals `origin = Point {x: 1, y: 2}`, `name = "héllo"`, `s = Shape::Circle(…)` with children `0`, `1`, `bag.items = [4, 5]` and `bag.label = "two"`; evaluate `xs[1] * 10 = -20`, hover, `-exec print 6 * 7`; `setVariable total = 41`, which the program then prints; step in, arguments `p`, `dx`, the caller's locals, step out; a division by zero stopping in `ratio` with `a = 7`, `b = 0` and `division by zero` at `debuggee.my:29:14`; stop on entry, a function breakpoint, exit code 3; a conditional breakpoint `i == 5`, a breakpoint set while running, pause, terminate; a type error failing the launch; Run Without Debugging). The same tests pass against the bundle (`MYLA_DAP_BUNDLE=1`) and with the Python CLI building (`MYLA_CLI=myla.py`).
- `tests/burn/test_vscode_debugger.py` runs the integration test with the Python CLI and with the self-hosted CLI (2 tests, 17 s); `tests/unit/test_vscode_extension.py` runs the unit tests under node without `npm ci`.
- Before the adapter existed the tests failed to import `src/debug/mi.ts` (`ERR_MODULE_NOT_FOUND`); the integration test first failed on a marker lookup of its own (`bp:call` matched `bp:callee`), then passed.
- An excerpt of the first session's DAP transcript is on [[Development/Debugging]] (`DAP_TRANSCRIPT=<file> npm test` writes the whole one).
