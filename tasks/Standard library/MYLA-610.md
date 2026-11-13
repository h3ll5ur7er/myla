---
id: MYLA-610
title: "Code comments give no unpinned timing (D197's sweep)"
type: chore
status: review
priority: low
labels: [std, comments, check-time, round-6]
---
Found by [[Project/Review-2026-11-12]] (the line on [[MYLA-554]]: the comments that keep helpers private "for the import cost" were measured before lazy modules, now 1.7 percent) and listed by [[MYLA-554]], which edits no `.my` file. Two comments in `lib/std/` quote a check cost measured before the loader read a library module's bodies only once called ([[MYLA-359]], [[MYLA-412]], [[MYLA-413]]):

- [[lib/std/task.my#L498-L502]], above `Fifo`: "(`std.deque` would do, but importing it costs every program that imports `std.task` about 2.5 ms of checking.)" (written with [[MYLA-351]])
- [[lib/std/time.my#L28-L32]], above `pad`: "Not `std.fmt`'s own: importing it and `std.num` would cost every program that imports `std.time`, `std.test` among them, 16 ms of checking." (written with [[MYLA-334]])

The comments of the same kind that [[MYLA-553]] wrote already give a figure measured with the lazy modules ([[lib/std/fs.my#L735-L738]], [[lib/std/net.my#L1727-L1730]], [[lib/std/archive.my#L1076-L1080]], [[lib/std/compress.my#L2402-L2406]]), and so does [[selfhost/checker.my#L4480-L4485]].

Measured by [[MYLA-554]] on `2ceef83` (`valgrind --tool=callgrind`, `build/myla check` with the library the tool carries, instructions of the whole run):

| Program | Instructions | Added |
| --- | --- | --- |
| `fun main() {}` | 20.7 M | |
| `import std.task as task` | 25.2 M | |
| … and `import std.deque as deque` | 26.2 M | 1.0 M, 3.9 % |
| … and `deque.new()`, `push_back`, `pop_front` called | 27.6 M | 2.4 M, 9.4 % |
| `import std.time as time` | 29.8 M | |
| … and `import std.fmt as fmt`, `import std.num as num` | 45.1 M | 15.2 M, 51 % |

So the reason in std.time's comment still holds (its 16 ms is stale: about 15 M instructions now, 3 to 5 ms by wall time on the shared container), and std.task's is weaker than it says (about 1 M instructions for the import, 2.4 M with what `Fifo` would call). The review's 1.7 percent is its own figure, and it doesn't say which import it measured.

**Widened to D197** (2026-11-13, the owner, as refined the same day): a timing in a code comment (Myla, Python, shell, the extensions; docstrings and comment-like strings of the tests count) stays only as a comparison with something else ("C took 10 s, Myla 20 s"; "before the change 12 ms, now 7 ms"; a percentage faster or slower), or pinned with the date and short hash of the commit it was measured at, `(2026-11-13, 748f3c2)`. A bare figure goes when the comment's reason stands without it, and is pinned otherwise. Durations that are behaviour or configuration (a timeout, a sleep, a test's deadline), units in an API's documentation and measures that aren't time (instructions, bytes) aren't timings. The wiki and the tasks keep their measurements.

- [x] Each comment gives a figure measured with the lazy modules (instructions and a percentage, as [[MYLA-553]]'s do), or goes with its reason: both figures went, the reasons stay ("would cost every program that imports `std.task` check time")
- [x] For `std.task`'s `Fifo`: decide whether `std.deque` now does: `Fifo` stays. The import still costs every importer of `std.task` 1.0 M instructions (3.9 %), 2.4 M (9.4 %) with the calls `Fifo` makes, for a queue of about thirty lines
- [x] Every code comment outside `docs/` and `tasks/` swept for D197: bare timings dropped, comparisons kept
- [x] The changed `.my` files check and their cases pass; the bootstrap reaches its fixed point; `scripts/test.sh fast`

## Evidence

Candidates: the task's grep, `grep -rnE "(//|#).*[0-9][0-9.,]* ?(ms|µs|us|ns|s|sec|seconds?|minutes?|min)\b" lib selfhost tools scripts tests examples --include=*.my --include=*.py --include=*.sh --include=*.mjs --include=*.js --include=*.ts` (156 lines, most of them `#test` cases of std.time, std.toml and std.bench, which aren't comments), and a scan that joins consecutive comment lines (a figure on one line and its unit on the next), adds percentages and the words faster, slower, twice as, took, of the run, check time, over `lib`, `selfhost` (not `embedded_std.my`), `tools`, `scripts`, `tests`, `examples`, `benchmarks`, `editor`, `vscode-extension` and `grammar` (143 comment blocks), Python docstrings and bare strings (20), and the Myla comments in the programs the Python tests carry (3). About 75 of those hold a timing or a percentage of one; the rest are behaviour, API units, counts or no timing at all.

- **Edited: 22 comments** (and the skip reason beside one): 7 in `lib/std` (`task.my`, `time.my`, `fs.my`'s 0.3 ms, `fmt.my`'s 2.7 s, `str.my`'s 2.6 s, `rt.my`'s 99 percent of a CPU, `compress.my`'s 3 ms), 4 in `selfhost` (`checker.my` twice, `harness.my`, `interp.my`), 3 in `scripts` (`test.sh`, `check-seed.sh`, `update-seed.sh`), 8 in `tests/burn` (`_targets.py`, `test_compiler_parity.py`, `test_literal_columns.py`, `test_selfhost_interp.py`, `test_term.py` twice, `test_time.py` twice).
- **Kept as comparisons: 30**, as they were: `log.my` (a fifth of a written line), `bigint.my`, `url.my`, `btree.my`, `fmt.my`, `rt.my`'s 14 %, `encoding.my`, `text.my`, `toml.my`, `regex.my` (two), `compress.my`'s gunzip, `bitset.my`, `yaml.my`, `num.my`, `checksum.my`, `io.my`, `bench.my`, `interp.my`'s 28 percent, `codegen.my`, `tools/wasm/node_fs.mjs`, `test_map_remove.py` (three), `test_compiler_parity.py`'s 14 s, `test_stdio.py`, `test_selfhost_parser.py`, `test_selfhost_interp.py` (two), `test_small_copies.py`.
- **Kept as behaviour or configuration**: std.http's defaults and keeper period, std.bench's and std.time's formats, the tests' sleeps, ticks, deadlines and limits, `scripts/test.sh`'s 4-second line between `fast` and `all`, figures computed from them (`test_stdio.py`'s 0.64 s, `test_generated_extremes.py`'s 47 minutes).
- **Pinned with a date and hash: none**; every bare figure's reason stands without it.
- Not edited, not time: instruction counts and their percentages (`fs.my`, `net.my`, `archive.my`, `compress.my`, `http.my`, `list.my`, `selfhost/checker.my:4480`'s 1.4 %, `selfhost/parser.my:628`'s 0.25 percent, `ir_x86.my`'s 1.6 %), memory (`interp.my`'s 600 MB), cycles (`codegen.my`, `runtime_x86.my`).
- Checks: `build/myla check` (with `--stdlib lib` for `lib/std`) on every changed `.my` file, `build/myla test` on the changed `lib/std` modules, all passing; `scripts/bootstrap.sh` reaches its fixed point, and the compiler and the CLI that `build/stage3` builds from `selfhost/` with and without the comment edits are byte-identical; `scripts/test.sh fast`.
