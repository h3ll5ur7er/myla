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

## Evidence

- The first seed: 6,211,242 bytes (the 6,210,821 of the fixed point and a six-line header), from commit a2f95ba, made by `scripts/update-seed.sh --from-python`.
- From the seed, the bootstrap reaches the byte-identical fixed point (6,210,821 bytes), and its `stage3.s` equals the seed's assembly byte for byte. The whole script (stages 0–3, `build/myla`, the language server and their checks) takes 7.4 s from the seed against 16.4 s with `--from-python`.
- An older seed: the `stage3.s` of commit b4100ff (before [[MYLA-237]] changed code generation, 6,194,029 bytes) as the seed bootstraps today's sources to the same fixed point, and its `stage3.s` equals the one from the current seed.
- The burn tests from the seed, cache empty: `test_compiler_parity.py`'s 159 tests in 28.6 s (36 s when stage 1 came from the Python backend); the cache holds `stage0`, `stage1`, `stage2` and the tools.

