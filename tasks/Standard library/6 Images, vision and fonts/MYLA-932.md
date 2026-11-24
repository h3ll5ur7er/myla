---
id: MYLA-932
title: "std.compress: LZW (GIF and TIFF) and PackBits"
type: feature
status: review
priority: medium
labels: [stdlib, compression, images]
---
Step 1 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]. The codecs GIF and TIFF need, beside DEFLATE.

- **Owns:** the new parts of `lib/std/compress.my`, [[Language/Standard-library/Compress]]
- **Needs:** [[MYLA-931]] (the bit readers), [[MYLA-930]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [x] `lzw_decode_gif(b, min_code_size, max_output)` and `lzw_encode_gif`: LSB-first, codes growing to 12 bits, clear and end codes, a full table kept (deferred clear) as decoders must accept
- [x] `lzw_decode_tiff(b, max_output)` and `lzw_encode_tiff`: MSB-first, the "early change" by one code, and the old-style (LSB) variant detected as libtiff does
- [x] `packbits_decode(b, max_output)` and `packbits_encode`
- [x] Each decoder bounded by `max_output` (`TooLarge`), as inflate is ([[MYLA-423]]); a code past the table is `Corrupt` (the existing `BadCode`: see Evidence)
- [x] Against Pillow's GIF and TIFF LZW (vendored streams), and round trips of random and repetitive data
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node): all but aarch64, which this machine can't run (no `qemu-aarch64`)
- [x] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered

## Evidence

Branch `stdlib/MYLA-932`, from `claude/stdlib-image-vision-plan-gm6jy5` at `0ad529e`.

**API** (all in `std.compress`, [[Language/Standard-library/Compress#lzw-and-packbits]]):

- `lzw_decode_gif(b: [uint8], min_code_size: int, max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>`, `lzw_encode_gif(b: [uint8], min_code_size: int) -> [uint8]`
- `lzw_decode_tiff(b: [uint8], max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>`, `lzw_encode_tiff(b: [uint8]) -> [uint8]`
- `packbits_decode(b: [uint8], max_output: int = 0x7FFFFFFF) -> Result<[uint8], CompressError>`, `packbits_encode(b: [uint8]) -> [uint8]`

Errors: a code past the table (or an entry code right after a clear) is the existing `BadCode`, whose meaning was widened, rather than a new `Corrupt`; a PackBits run cut short is `Truncated`; more output than `max_output` is `TooLarge` (checked before each string or run is copied); one new variant, `BadCodeSize` ("invalid LZW minimum code size", code -13), for a GIF minimum code size outside 1 to 8, because `BadHeader`'s message names gzip and zlib. Encoders panic on a programming error: `min_code_size` outside 2 to 8, or a byte that doesn't fit it. A `max_output` below 0 panics as for `inflate` (D184).

Decisions: one LZW core for both forms, parameterised by bit order and early change (0 or 1); width grows when the next entry `>= (1 << width) - early` (with `>=`, so GIF's degenerate minimum code size 1 grows as giflib does). The decoder keeps each entry as (start, length) in the output it already wrote, so a string is copied from there, no prefix chains. The data ends at the end code (what follows is ignored) or with the input (no end code needed, as libtiff and browsers accept; image decoders count their pixels). The GIF encoder clears when the table reaches 4096, the TIFF one before entry 4094 (libtiff's rule), both after a leading clear.

**Private helpers to be replaced:** `CodeReader` (LSB-/MSB-first code reader) and `CodeWriter` (its writer) in `lib/std/compress.my`, to become std.bytes's `BitReader`/`BitWriter` ([[MYLA-931]]). Also `PackBitsWriter`, a two-field struct that only exists because a function can't mutate a list it is passed (it can stay).

**Tests, before and after (soft TDD):** with the public functions stubbed (`Ok([])`/`[]`), `build/myla test lib/std/compress.my --stdlib lib` gave 164/208 passed (every new case but the few whose answer is empty failed); with the code 207/208, the one failure a wrong hand-made vector (`01` is the codes 1 and 0, not 1 alone), fixed to `29`. Now the module has 209 cases (155 before, 54 new), all passing interpreted (51 s), natively (`--native`) and on wasm32 under Node (`MYLA_EMULATOR="node tools/wasm/run.mjs" ... --target wasm32-wasi`). aarch64 wasn't run: no `qemu-aarch64` here.

**Burn test** `tests/burn/test_lzw.py` (4 tests, 12 s): OK. The corpus `tests/burn/data/lzw/` (30 streams, 395 KB, `python3 -m tests.burn.test_lzw --vendor`): GIF LZW from Pillow 13.0.0 (minimum code size 8; interlaced and not; noise that fills the table, a flat image, 1×1) and ImageMagick 6.9 (2, 4, 16, 64 and 256 colours: code sizes 2, 2, 4, 6, 8), TIFF LZW and PackBits strips from libtiff (via Pillow) and ffmpeg (grey, RGB, random RGB, bilevel); each expected output checked when vendoring against both Pillow's decoding and the test's own Python decoder. Natively, plain and `--checked`: every stream decodes to its bytes, and `TooLarge` with `max_output` one byte short. The encoders on 11 kinds of input (empty, 1 and 2 bytes, random 10 and 70000, 200000 zeros, runs of 1 to 300, periodic, 300 KB of the repository's text, a picture, pairs), GIF at code sizes 2, 3, 5, 7, 8: back through the module, through the Python decoder, and through Pillow inside a GIF or TIFF file the test writes (more than 40 such checks); also interpreted on three inputs. Fuzz: 3000 mutations of the corpus (cut, bit flips, bytes changed, bytes inserted, random data, other code sizes, small `max_output`): each answer equal to the Python decoder's (bytes or error message), plain and `--checked` builds identical, no runtime error; every outcome (Ok, `BadCode`, `TooLarge`, `BadCodeSize`, `Truncated`) occurs. `test_compress`, `test_archive`, `test_doc_blocks`, `test_examples_run`, `test_examples_compile` and `test_examples_tests` pass too.

**Speed**, natively, best of 5, 4 MB each (`python3 -m tests.burn.test_lzw --bench`, 2026-11-24, shared 4-core machine): a 2048×2048 picture: GIF LZW encode 54 ms (77 MB/s), decode 32 ms (133 MB/s); TIFF LZW 62 ms / 34 ms; PackBits 19 ms / 6.4 ms. Text: GIF LZW 59 / 34 ms; random bytes 66 / 39 ms; zeros 28 / 6.6 ms, PackBits 4.7 / 4.2 ms. Pillow on the same picture: its GIF codec 46 / 29 ms, libtiff's LZW 43 / 16 ms, PackBits 15 / 1.1 ms. The encoder's first hash (`(byte << 5) ^ prefix`, compress(1)'s) took 472 ms on the text (clustering); Knuth's multiplier 59 ms.

**Outside the owned files:** the module's row in [[Language/Standard-library]], the std.compress section of both copies of the skill's `reference/stdlib.md`, `examples/lzw_and_packbits.my` and its registration in `tests/burn/test_examples_run.py` and `test_examples_compile.py`.

**Toolchain bug found:** a `match` used as a value whose arm is a block ending in `process.exit(1)` (`let v = match r { Ok(b) => b, Err(_) => { print("x"); process.exit(1) } }`) passes `myla check` and runs under `myla run`, but `myla build` fails with `runtime error: internal error: main can't be lowered to the IR: a call without a value used as one` (selfhost/codegen.my:2863). The burn driver works around it.
