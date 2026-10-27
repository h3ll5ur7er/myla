---
id: MYLA-80
title: Language server written in Myla
type: feature
status: in-progress
priority: medium
labels: [lsp, selfhost, editor]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). Supersedes [[MYLA-49]], [[MYLA-50]] and [[MYLA-51]], whose findings are requirements here. Needs [[MYLA-78]] and [[MYLA-79]].

The self-hosted front end (lexer, parser, checker, loader, diagnostics in [[selfhost/diag.my]]) already exists; the server is a native program built from it.

- [x] JSON-RPC over stdin/stdout with `Content-Length` framing; initialize/shutdown/exit; a document store with unsaved text passed to the loader for every open buffer (not just the current one, [[MYLA-49]])
- [x] Diagnostics published for the file the error is in ([[MYLA-10]]); debounce in the main loop (no threads)
- [x] Positions in UTF-16 (the rules of [[src/myla/lsp/positions.py]])
- [x] Document symbols, definition, references, hover, completion: port [[src/myla/lsp/]] and use its tests ([[tests/unit/test_lsp_features.py]], [[tests/integration/test_lsp_diagnostics.py]]) as parity tests against the Myla server
- [ ] From [[MYLA-51]]: keep the last good parse when the buffer doesn't lex or parse; resolve names through scopes and imports (the checker) instead of by name across the workspace; member completion triggered by `.`; refresh the workspace index on `didChangeWatchedFiles`
- [ ] Semantic tokens from the compiler's own lexer, so editors highlight exactly what the compiler sees
- [ ] The VS Code extension starts the Myla server ([[MYLA-53]]), and registers its `**/*.my` file watcher again once the server handles `didChangeWatchedFiles` (removed in [[MYLA-53]] because the Python server ignores it)

## Progress

### Step 1: protocol and diagnostics

D67 on [[Project/Decisions]]; the design is on [[Architecture/Editor-tooling]].

- `tools/lsp/` (`main.my`, `protocol.my`, `server.my`, `text.my`): framing over `std.io`'s `Reader`, `std.json` messages, full document sync, a document store whose texts the self-hosted loader reads instead of the files (`load_program_with`, overrides for every open document), diagnostics published for the file the error is in and cleared when a later check no longer finds it, UTF-16 ranges as wide as the word at the error. `scripts/bootstrap.sh` builds `build/myla-lsp` with stage 3 and smoke-tests it.
- Debounce without threads: a new primitive `__poll(fd, timeout_ms)` in all six places (both checkers, both interpreters, both native backends) behind `Reader.ready(timeout_ms)`; a change waits until nothing has arrived for 0.4 s, opening and saving check at once. Checking only when the reader's buffer was empty was tried first and isn't deterministic: a burst arriving in several reads was checked part-way.
- Bugs found on the way, each with a regression test that failed before its fix:
  - A `return` inside a `for` loop left the loop's reference to the iterated list (both backends) or map (Python backend) unreleased, so the list stayed allocated. This was the language server leaking 7 MB a check; found with a heap census in gdb (walking the arena's cell headers at exit, with each cell's allocation site from breakpoints on `__alloc`'s returns). Test: `STRESS_FOR_EARLY_RETURN_SRC`, the old self-hosted build peaked at 3.1 GB.
  - The Python backend reused a freed cell over 4 KiB only for a request of exactly its size, so a long-running program grew; large cells now have power-of-two classes, as the self-hosted runtime already had (`STRESS_LARGE_SIZES_SRC`: arena exhausted after 18 s before, 0.27 s and 11 MB after).
  - The self-hosted backend's `?` copied the whole operand into the function's result, which can be smaller: `build/myla build` crashed (exit 139) after printing a type error. Test: `try_with_a_larger_success_payload`, and the bootstrap now checks that `build/myla build` and `run` exit with 1 on a type error.
  - The self-hosted backend didn't release a map value it overwrote (the server kept every version of a document): `__map_set_slot` now says whether the key was there. Test: `STRESS_MAP_OVERWRITE_SRC`, 312 MB peak before, under the 30 MB bound after.
- The Python server's diagnostics test became shared scenarios (8, up from 2) that both servers run.

Evidence:

- `tests/burn/test_lsp.py`: 22 tests (11 for each backend's build), 12 s. The memory test fails with the loop fix reverted (RSS +146 MB over 200 checks) and passes with it (< 256 kB).
- Checks: 0.5 ms for `examples/hello.my`, about 230 ms for `selfhost/checker.my` (5,000 lines and its imports); RSS flat at 25.2 MB over repeated checks of it (before the fixes: +7.4 MB a check, 772 MB after 100).
- Full run: 491 unit, 10 integration and 443 burn tests pass; the bootstrap reaches its fixed point at 7,794,199 bytes, then builds and smoke-tests the CLI and the server.

### Step 2: symbols, definition, references, hover, completion

- `tools/lsp/symbols.my` (the outline; selection ranges from the name token as in MYLA-48, full ranges to the declaration's last token), `features.my` (identifiers from the compiler's tokens, hover text, member-completion context, UTF-16 offsets back to code points), `workspace.my` (every `.my` file under the roots via `find`, skipping the directories the Python index skips, sorted, declarations cached by file content); the server answers `documentSymbol`, `definition`, `hover`, `references` and `completion` and advertises them.
- Deliberate differences from the Python server: a symbol's full range ends at its last token rather than at the last line an AST node is on (which drops the closing brace), and workspace files are visited sorted rather than in file-system order.

Evidence:

- `tests/integration/test_lsp_requests.py`: the 19 cases of `tests/unit/test_lsp_features.py` (selection ranges, outline, definition with workspace fallback, references with and without the declaration and across files, hover, completion after a dot and after astral characters) as protocol requests; the Python server passes them, and so do both builds of the Myla server (38 tests in `tests/burn/test_lsp.py`), all on the first run.
- A comparison with the Python server (`TestAgainstThePythonServer`, needs pygls; CI's burn job now installs it): document symbols of 63 files (examples, compiler, tools, std) equal except for range ends, and definition, hover, references and completion at about 360 sampled identifiers and 60 completion points in `examples/`. Changing `[K: V]` to `[K:V]` in the type rendering makes 7 files fail.
- Speed on `selfhost/checker.my`, workspace the whole repository (Python / Myla): documentSymbol 487 / 134 ms, definition 664 / 189, hover 480 / 147, references 994 / 160, completion 1,974 / 826 ms, the same number of results each.
- Full run: 491 unit, 29 integration and 484 burn tests pass; the bootstrap reaches its fixed point (unchanged, 7,794,199 bytes) and builds the server.

Next: semantic tokens from the compiler's lexer, the MYLA-51 improvements (scopes and imports through the checker, keeping the last good parse, member completion by type, `didChangeWatchedFiles`), then the VS Code extension.
