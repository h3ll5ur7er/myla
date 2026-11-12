---
id: MYLA-555
title: "R13 The review's generators as burn tests"
type: improvement
status: todo
priority: medium
labels: [testing, burn, differential, round-6]
---
Work package R13 of [[Project/Review-2026-11-12]]. Files: `tests/burn/` and `.github/workflows/` only, so it can run beside every other lane. Each round-5 package pinned one program per reported bug; the review's generators found every older bug of this round within minutes. They are in the bundle.

- [ ] **Deep copies between tasks** (`repro-r5/native/gen.py` of `R5b/deep`): 35 value shapes through about 60 hand-overs each (actor store and get, `async let`, child results, channel, `task.all`, `task.pool`, async lambda), native against interpreted, at 1 and 8 threads. It finds [[MYLA-415]]'s crash once closures capture the recursive shapes
- [ ] **Writes into containers** (`gen_h4.py`, `gen_loc.py`): about 5,400 statements over int, str and list elements, struct fields and locals, in plain, async and lambda contexts
- [ ] **Reads beside a mutation** (`gen_rd.py`): 90 forms; it finds [[MYLA-543]]'s use-after-free
- [ ] **Generic code per width** (`repro-r5/interp/gen.py`): 320 programs, trap positions included
- [ ] **Extreme arguments** (`repro-r5/std/gen.py`, `harness.py`): one call per function with boundary values, under `myla run`, plain and `--checked`; it finds [[MYLA-550]]'s `bit_len`
- [ ] The burn drivers of the format parsers (YAML, TOML, JSON, XML, INI, CSV) built `--checked` as well, as `test_archive`'s is; it finds [[MYLA-550]]'s YAML trap
- [ ] The Go half of `test_regex` runs in CI (the workflow installs no Go, so it skips silently): install Go there, or fail under `MYLA_REQUIRE_TARGETS`
- [ ] `TimeLimits.test_idle_non_reading_and_slow_handled_connections` failed once in 9 runs under load (`8388652 not less than 8388608`): wait past `write_ms` before reading the held sockets
- [ ] A size for each that fits the suite: the full generators ran minutes per runner; a seeded sample in the suite, the full run behind a variable
