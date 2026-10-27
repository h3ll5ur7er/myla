---
id: MYLA-83
title: Retire the Python tools that have Myla replacements
type: chore
status: review
priority: low
labels: [cleanup]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). The last step, one tool at a time, as was done for the compiler: once a Myla tool passes the parity tests of its Python counterpart, the Myla one becomes the default and the Python one is removed or kept only as the bootstrap/reference.

- [x] Language server ([[MYLA-80]]): remove [[src/myla/lsp/]] and the `myla lsp` command
- [x] `myla test` ([[MYLA-81]]) and `run`/`build`: decide which Python commands stay for the bootstrap
- [x] Decide the long-term role of the Python interpreter (the semantics reference) and record it on [[Project/Decisions]]

## How

Decided with the user and recorded as D71 on [[Project/Decisions]]: the Python toolchain stays as the bootstrap (stage 1) and the semantics reference (the oracle of the self-hosting gates and of the `myla test` parity gate), with its commands `run`, `test`, `build`, `check`, `tokenize`, `parse`; everyday use is `build/myla` and `build/myla-lsp`; tools beyond the compiler exist only in Myla.

- Removed `src/myla/lsp/` (the pygls server, 1,350 lines), the `myla lsp` command, the `lsp` extra (pygls, and its dependencies in `uv.lock`), the pygls installs in CI, and the Python server's tests: `tests/unit/test_lsp_adapter.py`, `tests/unit/test_lsp_features.py`, and the Python classes of `tests/integration/test_lsp_diagnostics.py` and `test_lsp_requests.py`. Their scenario classes and protocol client moved to `tests/burn/_lsp_scenarios.py`, still run against the Myla server by both builds; the comparison with the Python server in `tests/burn/test_lsp.py` went with it (the corpus tests and the checker oracle for member accesses stay).
- The VS Code extension starts only `build/myla-lsp` (or `myla.serverPath`) and says how to build it when it is missing; `myla.server` and `myla.pythonPath` are gone.
- `myla repl` in the Python CLI already points to `build/myla repl` ([[MYLA-82]]).
- Docs: [[Architecture/Editor-tooling]] describes the one server (the Python one in a paragraph of history), [[Getting started]], [[Home]], [[Architecture]], [[Development/Testing]], [[Development/Conventions]], the extension's README and CHANGELOG.

## Evidence

- The suites without the Python server: 469 unit tests (26 fewer: its features and compiler adapter), 2 integration tests (27 fewer: the scenarios now run only against the Myla server, from `tests/burn/_lsp_scenarios.py`), 536 burn tests (the two comparisons with the Python server gone); all pass. `myla --help` lists no `lsp`; `uv lock` removed pygls and typing-extensions.
- The extension: `npx tsc -p ./` passes; `TestExtensionStartsTheServer` (4 tests) covers the repository's built server, a configured binary, the message when there is none, and that the command picked starts a server answering `initialize`.
- The bootstrap fixed point stays at 7,794,199 bytes and stage 3 builds `build/myla-lsp`.
