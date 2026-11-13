---
id: MYLA-555
title: "R13 The review's generators as burn tests"
type: improvement
status: review
priority: medium
labels: [testing, burn, differential, round-6]
---
Work package R13 of [[Project/Review-2026-11-12]]. Files: `tests/burn/` and `.github/workflows/` only, so it can run beside every other lane. Each round-5 package pinned one program per reported bug; the review's generators found every older bug of this round within minutes. They are in the bundle.

- [x] **Deep copies between tasks** (`repro-r5/native/gen.py` of `R5b/deep`): 35 value shapes through about 60 hand-overs each (actor store and get, `async let`, child results, channel, `task.all`, `task.pool`, async lambda), native against interpreted, at 1 and 8 threads. It finds [[MYLA-415]]'s crash once closures capture the recursive shapes
- [x] **Writes into containers** (`gen_h4.py`, `gen_loc.py`): about 5,400 statements over int, str and list elements, struct fields and locals, in plain, async and lambda contexts
- [x] **Reads beside a mutation** (`gen_rd.py`): 90 forms; it finds [[MYLA-543]]'s use-after-free
- [x] **Generic code per width** (`repro-r5/interp/gen.py`): 320 programs, trap positions included
- [x] **Extreme arguments** (`repro-r5/std/gen.py`, `harness.py`): one call per function with boundary values, under `myla run`, plain and `--checked`; it finds [[MYLA-550]]'s `bit_len`
- [x] The burn drivers of the format parsers (YAML, TOML, JSON, XML, INI, CSV) built `--checked` as well, as `test_archive`'s is; it finds [[MYLA-550]]'s YAML trap
- [x] The Go half of `test_regex` runs in CI (the workflow installs no Go, so it skips silently): install Go there, or fail under `MYLA_REQUIRE_TARGETS`
- [x] `TimeLimits.test_idle_non_reading_and_slow_handled_connections` failed once in 9 runs under load (`8388652 not less than 8388608`): wait past `write_ms` before reading the held sockets
- [x] A size for each that fits the suite: the full generators ran minutes per runner; a seeded sample in the suite, the full run behind a variable

## Evidence

The generators are modules of `tests/burn/` (`_gen_deep.py`, `_gen_writes.py`, `_gen_reads.py`, `_gen_widths.py`, `_gen_extreme.py`), ported from the bundle with their programs unchanged, and `tests/burn/_differential.py` runs them: a generator's cases behind a `main` that starts at the case its argument names and prints a mark after each, run on each runner at once and restarted after a case that ends the program (a trap, a signal, `out of memory`, a time limit per case), so each case gets its own answer, as the review's `harness.py` did. A case that fails today is in its test's `KNOWN` map with the task; it must still fail (the test fails when it passes: the fixing lane removes its entry) and every other case must pass. The suite runs a sample drawn from a fixed seed with the known failures in it; `MYLA_GENERATED=full` runs everything, `MYLA_GENERATED_SEED` draws another sample. With `MYLA_TEST_TARGET` the builds are the target's; all six modules are in `_targets.SUITES`.

| Test | What runs (suite / full) | Runners | Host | aarch64 | wasm32 | Known (task) |
| --- | --- | --- | --- | --- | --- | --- |
| `test_generated_deep_copies` | 41 shapes (the review's 35 and 6 closures capturing the recursive enums), 4 rounds / 20 | interpreted, native (default, 1 and 8 workers), `--checked` | 10 s | 68 s | 66 s | the 6 closure shapes segfault on x86-64 and aarch64 ([[MYLA-415]], B1); wasm32 passes them |
| `test_generated_reads` | all 89 forms | interpreted, native, `--checked` | 0.5 s | 1 s | 5 s | 25 forms ([[MYLA-543]], B2), on every target |
| `test_generated_writes` | 12 programs, 150 cases each / about 10,000 | the three | 18 s | 81 s | 48 s | 4 `g[g.k()].push(g.v())` orders per locals program ([[MYLA-543]], C9); 30 `op=` and `x[i] = x[i] + v()` on str elements ([[MYLA-543]], B2) |
| `test_generated_widths` | 10 safe programs and 10 traps per integer type / 356 traps | safe: the three; traps: interpreted and `--checked` (a plain build wraps, and some never end) | 11 s | 33 s | 25 s | none (all 366 pass in full) |
| `test_generated_extremes` | 300 calls a group and the slow ones on the builds / about 17,400 | the three | 40–70 s | 103 s | 109 s | `bigint.shl(2^31 - 2).bit_len()` ([[MYLA-550]]) |
| `test_formats_checked` | 1,000 generated and 1,000 broken documents per format and about 40 at the limits / ten times as many | plain and `--checked` | 4–7 s | 25 s | 18 s | YAML hex and octal scalars past int64 ([[MYLA-550]], B5) |

Before/after: with the `KNOWN` maps emptied, `test_generated_reads` fails with `25 of 89 cases fail` and `test_generated_deep_copies` with `6 of 41 cases fail` (signal 11 natively, `bad=0` interpreted); `test_formats_checked.test_yaml` failed on `mask: 0x8000000000000000` (`ok = {"mask":9.223372036854776e+18}` plain, `integer overflow` at `yaml.my:1139` checked) until it joined the list. `MYLA_GENERATED=full` of deep copies, reads, writes and widths: 24 tests OK in 176 s; of the extreme arguments: 5 tests OK in 1,982 s (the interpreter's slow cases take most of it); of the formats: 6 OK in 29 s. At integration, with wave 1's fixes merged ([[MYLA-415]], [[MYLA-543]], [[MYLA-550]]), every known failure passed and the `KNOWN` maps are empty; the six tests pass (35 tests, 70 s). The full extreme run (by the trial harness, before the rules below): num 20, int 148, time 0, cont 114, seq 31 disagreements, every one explained below.

The suites (times under the shared machine's load, about 8 on 4 cores): `scripts/test.sh fast` 868 tests OK (1,062 s); `scripts/test.sh` 1,583 tests OK, 342 skipped (1,540 s, with the YAML test suite and xmlts given).

Rules the extreme-argument test needed (proposed; the owner may decide otherwise):
- std.int's arithmetic methods (`pow`, `abs`, `gcd`, `lcm`, `div_euclid`) and the sums of lists and iterators overflow as the operators do (D175): where `myla run` and `--checked` both end in `integer overflow` there, the plain build's wrapped value isn't held to them (the 148 of `int` and 26 of `cont`). The alternative, D184 (2) for them too (a named error in every build), would make them the only arithmetic that never wraps.
- Calls that make 2^30 things (a string of that many digits, a grid, deque, bitset, union-find, dense graph, list, padding or builder of that size) are left out: `out of memory` natively under the run's 1 GiB, minutes interpreted, an answer of neither (`NEVER`).
- Calls that take seconds interpreted (`ldexp` at |k| ≥ 2^30, [[MYLA-580]]; `bigint.shl` by 2^30 and more; a million characters of padding) run on the two builds in the suite and on all three in full (`SLOW`).
- `now.add(time.hours(2562047))` is left out: whether it fits beside the monotonic clock depends on the machine's uptime (47 minutes) and differs under Node.

The other items:
- `test_regex`: CI's burn job installs Go (`actions/setup-go`, Go 1.24) and prints its version; `GoOracle.test_go_is_there` fails under `MYLA_REQUIRE_TARGETS` without `go` (checked with `PATH=/usr/bin:/bin`: FAILED; with Go: OK, and `test_go_interpreted` OK).
- `TimeLimits`: the cause is the order of the test, not the server: it read the two non-reading clients right after the quick GET, and under load the second holder's handler starts late, so its `write_ms` hadn't passed and the test's read was progress that let the whole response through (8,388,652 bytes = headers and 8 MiB). It now waits until the server holds only its listener (its sockets in `/proc/<pid>/fd`, at most 10 s) and then reads; it passed alone (24 s, both servers).
- New bug: [[MYLA-580]] (`math.ldexp` takes |k| / 1023 steps). No other generated case failed beyond those of the known tasks.

