---
id: MYLA-218
title: "The bootstrap from a committed assembly seed"
type: feature
status: review
priority: high
labels: [bootstrap, selfhost]
---
D101 ([[MYLA-201]]): stage 1 of the bootstrap is built from a committed assembly file, the self-hosted compiler's own output, instead of by the Python toolchain. The stage-3 assembly is 6.2 MB today (626 KB with gzip, about what Git stores per version).


Backup: the branch `backup/python-toolchain-final` (commit d94f948) is the last state before this work, with the whole Python toolchain ([[Development/Bootstrap]]).
- [x] `bootstrap/seed.s`: the stage-3 assembly of `selfhost/gen_main.my`, with a header comment naming the commit and the fixed point it came from; `.gitattributes` marks it `-diff linguist-generated`
- [x] `scripts/bootstrap.sh`: stage 1 from the seed (`as`, `ld`), then stages 2 and 3 and the fixed point as today; the Python stage 1 stays available behind an option until [[MYLA-219]]
- [x] `scripts/update-seed.sh`: regenerates the seed from a verified fixed point; [[Development/Bootstrap]] says when (before the compiler's own source uses a construct the seed lacks; otherwise at will) and how to check a seed (regenerate and compare)
- [x] CI: the bootstrap job starts from the seed, without Python (that job checks the seed still builds the current compiler to the fixed point), then once more with `--from-python`; the test-tools cache key includes the seed
- [x] Measured: the bootstrap's time from the seed against the time from Python
- [x] The burn tests bootstrap from the seed (`tests/burn/_tools.py`): no Python backend in the tests but the fallback ([[MYLA-235]])

- [x] The seed stays current (the owner's choice: a CI check and an optional pre-push hook, not a seed per commit): `scripts/check-seed.sh` in CI's `bootstrap` job, `.githooks/pre-push` turned on by `scripts/install-hooks.sh`; the rule in [[Development/Conventions]] and `AGENTS.md`
## Evidence

- The first seed: 6,211,242 bytes (the 6,210,821 of the fixed point and a six-line header), from commit a2f95ba, made by `scripts/update-seed.sh --from-python`.
- From the seed, the bootstrap reaches the byte-identical fixed point (6,210,821 bytes), and its `stage3.s` equals the seed's assembly byte for byte. The whole script (stages 0–3, `build/myla`, the language server and their checks) takes 7.4 s from the seed against 16.4 s with `--from-python`.
- An older seed: the `stage3.s` of commit b4100ff (before [[MYLA-237]] changed code generation, 6,194,029 bytes) as the seed bootstraps today's sources to the same fixed point, and its `stage3.s` equals the one from the current seed.
- The burn tests from the seed, cache empty: `test_compiler_parity.py`'s 159 tests in 28.6 s (36 s when stage 1 came from the Python backend); the cache holds `stage0`, `stage1`, `stage2` and the tools.
- Keeping it current: a seed-only update (stages 0–3 and the comparison) takes 4.9 s, `scripts/update-seed.sh` with the whole bootstrap 7.7 s, `scripts/check-seed.sh` 5.9 s (instant against an existing `build/stage3.s`). One seed version after a code-generation change ([[MYLA-237]]) adds 264 KB to the history (delta-compressed, measured in a scratch repository), so a seed per commit was declined. The seed's assembly doesn't depend on the checkout's location (a worktree elsewhere produces it byte for byte), so CI can compare.
- The check and the hook: with a changed compiler message in `selfhost/gen_main.my`, `check-seed.sh` exits 1 ("run scripts/update-seed.sh and commit bootstrap/seed.s"), and the pre-push hook given a push that touches the seed stops it; after `update-seed.sh` the check passes; a push that touches neither the compiler nor the seed skips the check.

