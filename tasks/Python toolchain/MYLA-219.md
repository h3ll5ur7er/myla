---
id: MYLA-219
title: "Retire the Python toolchain"
type: chore
status: backlog
priority: high
labels: [bootstrap, python, tests]
---
D101 ([[MYLA-201]]): from now on the Python toolchain gets no new features; once the seed bootstrap works ([[MYLA-218]]) it is removed, interpreter included ([[MYLA-202]]). The self-hosted interpreter becomes the reference the gates compare native code with. Doing this before the language round ([[MYLA-215]]) halves the cost of every change in it.

- [ ] An inventory of everything that runs `myla.py` or imports `src/myla`: the bootstrap, the burn gates (stage-by-stage comparison with the Python compiler, the parity corpus, the error corpus, the `myla test` parity gate), the unit and integration tests, CI, the extension's tests, scripts and the justfile
- [ ] The gates compare the self-hosted interpreter with native code built by the self-hosted backend; the error corpus is pinned by its expected texts; what only the Python tests covered gets a burn test or is dropped on purpose (listed)
- [ ] Commands only `myla.py` has (`tokenize`, `parse`, …) exist in `build/myla` where a test or a user needs them
- [ ] The standard library moves out of `src/myla/std/`, and the gdb pretty-printer out of `src/myla/debug/` (both compilers embed it, D82)
- [ ] `src/myla/`, `myla.py` and their tests removed; [[Architecture]], [[Development/Testing]], [[Development/Bootstrap]], [[Getting-started]], the README, `AGENTS.md` and the `myla` skill updated
