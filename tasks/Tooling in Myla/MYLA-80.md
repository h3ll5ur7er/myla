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
- [x] Semantic tokens from the compiler's own lexer, so editors highlight exactly what the compiler sees
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
- A comparison with the Python server (`TestAgainstThePythonServer`, needs pygls; CI's burn job now installs it): document symbols of 63 files (examples, compiler, tools, std) equal except for range ends, and definition and hover at 391 sampled identifiers (references at every fourth) and completion at 86 points in `examples/`. Changing `[K: V]` to `[K:V]` in the type rendering makes 7 files fail.
- Speed on `selfhost/checker.my`, workspace the whole repository (Python / Myla): documentSymbol 487 / 134 ms, definition 664 / 189, hover 480 / 147, references 994 / 160, completion 1,974 / 826 ms, the same number of results each.
- Full run: 491 unit, 29 integration and 484 burn tests pass; the bootstrap reaches its fixed point (unchanged, 7,794,199 bytes) and builds the server.

### Step 3: semantic tokens

D68 on [[Project/Decisions]]; described on [[Architecture/Editor-tooling]].

- `tools/lsp/semantic.my` answers `textDocument/semanticTokens/full`: token kinds from the compiler's lexer; strings and f-strings (split around their holes) measured in the source, since string tokens carry decoded text and the f-string lowering adds tokens that aren't in the source; comments found between tokens (block comments one span per line); identifiers classified from the outline and their neighbours.
- Profiling with callgrind took a request on `selfhost/checker.my` from about 500 ms to about 280 ms (token kinds by one `match` instead of comparison loops, an ASCII fast path for offsets). What remains is mostly the compiler's lexer and parser, a third of it in the derived `==` on `TokenKind`, a chain of 70 comparisons: filed as [[MYLA-87]].

Evidence:

- `tests/burn/test_lsp.py`, `SemanticTokenScenarios` on both builds: a 13-line sample with 64 expected (text, type, modifiers) triples, UTF-16 offsets after astral characters, no tokens for a file that doesn't lex, and the corpus property test on all 47 example and compiler files. With comment detection switched off, all 47 fail the coverage check.

### Step 4: robustness (MYLA-51, part 1)

- The last good parse: when a document doesn't parse, requests use the outline of the last text that did (remembered at open, after a check that found no lex or parse error in it, and at each request that parsed it); when it doesn't lex, identifier lookups use that text too. Semantic tokens stay on the current text.
- Completion triggers on `.`; `workspace/didChangeWorkspaceFolders` adds and removes roots (advertised under `workspace.workspaceFolders`); `workspace/didChangeWatchedFiles` is accepted and needs nothing, as workspace files are read at each request.
- Caches: a document's outline is reused while its text is the same; each workspace file keeps its declarations and an index of its identifiers while its text is the same, so `references` no longer lexes every file every time.

Evidence: `RobustnessScenarios` (5 tests, on both builds): a half-typed string keeps the outline, definition and hover; a parse error keeps the outline and completion; the trigger character; a folder added and removed; a workspace file edited on disk is seen. `references` on `selfhost/checker.my` (workspace: the repository): 365 ms per request before the caches, 65 ms after the first. Full run: 491 unit, 29 integration and 502 burn tests pass; the bootstrap builds the server.

Next: resolution by scope and imports (MYLA-51's main point), member completion by receiver type, fuller signatures, then the VS Code extension.

### Step 5: resolution by scope and imports (MYLA-51, part 2)

D69 on [[Project/Decisions]]; described on [[Architecture/Editor-tooling]].

- `tools/lsp/resolve.my` walks the parsed document with a stack of scopes: parameters, `let`/`var` (the initializer sees the outer name), `for` variables, match bindings (or-patterns declare once), lambda and type parameters, then the file's declarations and the names it imports. Imports are found by the loader's rules (relative, `std.*`, packages) and outlined from the open document or the file; `import m` makes `m.name` resolve. Variants (`Color.Red`, in patterns too) and fields in struct literals and patterns resolve through their type; attribute arguments are walked. Uses are keyed by identifier token, searched among identifier tokens only: the f-string lowering puts its `(`, commas and `)` at the string's start, out of order, which first resolved hole names to a later token.
- Definition, hover and references use it, and fall back to the lookup by name for what doesn't resolve (members through values, until step 6). References to a local are its uses; to a global, its name's occurrences less those resolving elsewhere in the document and other files' locals (the workspace cache now keeps each file's locals, from one lexing and parsing per file).
- Speed: a resolution is cached per document until its text changes or a notification arrives, module outlines while their text is the same (`checker.my` imports `ast.my` in six statements, which were outlined six times); an index of ASCII lines skips UTF-16 counting. References dedupe with key sets instead of pairwise comparisons.
- `build/myla-lsp --resolve <file>…` prints a resolution.

Evidence:

- `ScopeScenarios` (5 tests, both builds) failed before the server used the resolver (all 5) and pass after: a local and a parameter shadowing a function named like them, the loop variable, hover texts; references of the local, the function and main's `xs`; another file's local of the same name left out; `Color.Red` against `Light.Red`, `P`'s field against `Q`'s, struct-pattern bindings, type and lambda parameters; imports through an item, an alias, a module and `std.fs`, with a decoy declaration in a file that sorts first.
- `TestResolutionCorpus`: on the 65 sources of the repository (examples, compiler, tools, standard library), every name a file declares resolves wherever it is used outside a member access, a local only after its declaration, no position twice; both builds print the same 41,536 lines of declarations and uses. It caught three gaps while I wrote it (attribute arguments, later or-pattern alternatives, the f-string token order), and catches each again when reintroduced (8, 1 and 17 files fail).
- `TestAgainstThePythonServer` relaxed where the answers differ by design: a local's definition is a declaration of the name in the same file (the Python server answers nothing), references are a subset of the Python server's and include the identifier asked about; with local references cut to the declaration, 12 sampled positions fail.
- Timing on `selfhost/checker.my` (4,100 lines): resolving it cold with its imports 363 ms → 212 ms after caching module outlines; in the server a request takes about 20 ms when the resolution is cached and 330 ms after an edit. `references` to `TokenKind` in `selfhost/parser.my` (workspace `selfhost/`, 468 locations): 22 ms warm (28 ms before this step), 897 ms for the first request (730 ms before: the locals of each file).
- Full run: 491 unit, 29 integration and 514 burn tests pass; the bootstrap fixed point stays at 7,794,199 bytes and stage 3 builds the server.

Next: member completion by receiver type and fuller signatures (step 6), then the VS Code extension (step 7).

After [[MYLA-87]] (derived `==` on `TokenKind` as a tag comparison): on `selfhost/checker.my`, semantic tokens 280 → 174 ms, a request after an edit 322 → 193 ms, `--resolve` 217 → 127 ms.
