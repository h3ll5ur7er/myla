---
id: MYLA-153
title: A faster burn suite and honest test timings
type: improvement
status: done
priority: medium
labels: [testing, ci]
---
Split from [[MYLA-58]], whose tiers worked once: the burn suite has grown to 811 tests and takes about 4 minutes in CI (about 110 s outside the self-hosted gates), while [[Development/Testing]] promises a fast tier of about 20 s and contradicts itself on the timings.

- [x] Measure where the burn time goes (per module) and keep the slow, broad corpora (concurrency stress, the language server scenarios, the JSON corpus, the self-hosted gates) out of the fast tier
- [x] Testing.md's timings measured again and made consistent

## Evidence

- Each burn module timed on its own with the tools cached (4 cores, 2026-11-01): 320 s in all; `test_selfhost_cli` 57 s, `test_selfhost_codegen` 51 s, `test_lsp` 39 s, `test_compiler_parity` 36 s, `test_concurrency_stress` 22 s, `test_selfhost_interp` 22 s, `test_json` 17 s, `test_vscode_debugger` 11 s, then everything else under 9 s.
- `scripts/test.sh fast` now leaves out the self-hosting gates and the eleven modules of 4 s or more (the broad corpora: concurrency stress, the language server scenarios, JSON, TOML; the native parity, runtime and file-system suites): 18 s with the unit and integration tests (it took about 170 s before, leaving out only the gates).
- [[Development/Testing]]: one set of timings, measured, and the corpus counts (210 files).
