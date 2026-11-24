---
id: MYLA-945
title: "Image and font test corpus, the fuzz harness and the benchmarks"
type: chore
status: backlog
priority: medium
labels: [stdlib, images, tests]
---
Step 1 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]: what every codec lane plugs its files into.

- **Owns:** `tests/burn/data/images/`, `tests/burn/test_images.py`, `benchmarks/images_std.my`
- **Needs:** [[MYLA-930]] (the fixture decision)

- [ ] The corpus with a `LICENSES.md` naming each file's source and licence: PngSuite; a few JPEG (baseline, progressive, every sampling factor, restart markers, CMYK), GIF (animated, interlaced, transparent) and TIFF files; one small OFL font subset
- [ ] `--vendor`: Pillow writes the expected pixels as PAM files (or their SHA-256 where large), as test_toml's `--vendor` makes its JSON; the tests themselves need no third-party package, and skip only the round trips through Pillow when it is missing
- [ ] The harness: a driver per module, built once, natively and `--checked`; the smallest files also interpreted; `MYLA_TEST_TARGET` runs it on aarch64 and wasm32 (`scripts/test-target.py`)
- [ ] Fuzzing: every truncation up to 512 bytes and 10,000 seeded mutations per decoder; the pass condition "`Ok` or `Err`"; the seed printed on a failure
- [ ] The benchmark program and Pillow's numbers for the same work beside it, filled in as the modules land
- [ ] [[Development/Testing]] names the suite
