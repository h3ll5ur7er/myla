---
id: MYLA-235
title: "The burn suite compiles with the self-hosted compiler; Python is the fallback"
type: improvement
status: review
priority: medium
labels: [ci, tests]
---
D115 ([[MYLA-216]]): today pull-request burn tests run the CLI and language server built by the Python backend, and only the bootstrap job runs the real `build/myla`, on `hello.my`. The burn job bootstraps (from the seed once [[MYLA-218]] lands) and runs the suite against `build/myla` and `build/myla-lsp`.

The owner, on 2026-11-01: "primarily use the native compiler for tests, python shall only be the fallback from now on".

- [x] The tests bootstrap the compiler themselves, in the burn job, cached with the tools (`build/test-tools`, keyed by the sources in CI): no artifact needed
- [x] `tests/burn/_tools.py`: the Python backend builds stage 1, stage 1 compiles the compiler (at the fixed point the same as `build/stage3`), and that builds every tool (the CLI, the language server, the grammar tool, the stage tools), as `scripts/bootstrap.sh` does
- [x] `tests/burn/_native.py`: test programs built by the natively built CLI (`myla build`, from the entry file `check_file` records); `test_debug_info.py` builds through it too
- [x] `MYLA_TEST_BACKEND=python`: the Python backend builds everything, the fallback; tests that compare the two compilers, or a runner with the interpreter, still run both
- [x] [[Development/Testing]] describes it
- [ ] CI's job time on a runner, once this runs there (locally the burn suite takes the same time)

## Evidence

- Native by default: after a run, `build/test-tools` holds `stage1`, `stage2` and the nine tools, all built by `stage2` (`main`, `lsp`, `grammar`, `gen_main`, `check_main`, `lex_main`, `parse_main`, `interp_main`, `project_main`).
- The burn suite on the native path, from an empty cache: 836 tests pass in 450 s (the same as before, 430–500 s on this machine); `test_compiler_parity.py` alone: 159 tests in 36 s, the bootstrap included.
- The fallback: `MYLA_TEST_BACKEND=python` runs `test_compiler_parity.py`, `test_debug_info.py` and `test_fs.py` (206 tests) green in 51 s.
- Stage 1 still comes from the Python backend until the seed ([[MYLA-218]]).
