---
id: MYLA-431
title: "P17 Seed size"
type: improvement
status: done
priority: high
labels: [bootstrap, seed, repository, round-5]
---
Work package P17 of [[Project/Review-2026-11-09]], moved before wave A (the owner's choice, 2026-11-10): every round adds two seeds. Over half of each seed is the embedded standard library as `.byte` lists (10.5 of 19.4 MB); the seeds doubled in two days and each update adds about 3.4 MB to the pack.

- [x] Measure what the bootstrap reads of the seed's embedded library
- [x] Build the seed without the embedded library if the bootstrap never reads it, else emit strings as `.ascii`
- [x] Its own pull request: both seeds rewritten, the bootstrap's fixed point and `scripts/check-seed.sh` unchanged in meaning

## What was built

Stage 0 is only ever run by the bootstrap scripts and `tests/burn/_tools.py`, each time as `stage0 <entry> lib`, so it reads the library from `lib/` and never the copy it embeds. `seed_compile` in [[scripts/host.sh]] compiles `selfhost/gen_main.my` with an empty `selfhost/embedded_std.my` in its place (two functions returning `[]` and `""`) and restores the file afterwards, also on an interrupt. `scripts/update-seed.sh` writes every seed with it, and `scripts/check-seed.sh` compares every seed against it, the host's included, so a seed is no longer the bootstrap's `stage3.s` byte for byte. The compiler's sources, its output for programs and every tool the bootstrap builds are unchanged. The `.ascii` alternative was left: it would change every program's assembly and the wasm32 back end's reader of `.byte` lines, for less (the library's text stays in the seed).

## Evidence

- **Sizes:** `bootstrap/seed.s` 19,560,499 → 9,773,137 bytes; `bootstrap/seed-aarch64.s` 32,124,049 → 22,301,262 bytes. Compressed with `gzip -9` (a proxy for a version's cost in the pack): 1,735,450 → 979,407 and 3,033,993 → 2,275,247 bytes.
- **Same compiler:** a bootstrap from the new seed gives `stage3.s` and `build/myla` identical (`cmp`) to those of a bootstrap from the old seed, and reaches the byte-identical fixed point.
- **aarch64:** `MYLA_ARCH=aarch64 AS=aarch64-linux-gnu-as LD=aarch64-linux-gnu-ld MYLA_RUN=qemu-aarch64 scripts/bootstrap.sh` from the new `seed-aarch64.s`: byte-identical fixed point (32,123,554 bytes).
- **Seeds current:** `scripts/check-seed.sh` with a build directory and on its own bootstrap: both seeds are the current compiler; `selfhost/embedded_std.my` is left as committed.
- **Suites:** `scripts/test.sh fast`: 779 tests, OK (3 skipped), the burn tests' tools built from the new seed.

## Review 2026-11-12

Signed off in [[Project/Review-2026-11-12]], with a follow-up in [[MYLA-552]]: the seeds are 10.9 MB and 25.3 MB, but an update still costs the pack about 2.9 MB, as the labels renumber.
