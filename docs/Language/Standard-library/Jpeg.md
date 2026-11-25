# std.jpeg

JPEG decoding ([[MYLA-936]], D311, the plan [[Project/Standard-library-roadmap/Images-vision-and-fonts]]): baseline, extended sequential and progressive JPEG, Huffman coded, 8 bits a sample, gray, YCbCr, RGB and Adobe's CMYK and YCCK, every sampling factor libjpeg reads, restart intervals, and the metadata beside the pixels (JFIF's density, EXIF and its orientation, the ICC profile). It decodes to the same pixels as libjpeg with its defaults, bit for bit, so to what Pillow gives, on every target. The encoder is [[MYLA-937]]. Images are std.image's ([[Language/Standard-library/Image]]).

```myla
import std.jpeg as jpeg
import std.encoding as encoding

fun main() {
    // an 8x8 gray JPEG by Pillow: 72x96 dpi, EXIF orientation 6
    var b = encoding.hex_decode("ffd8ffe000104a46494600010101004800600000ffe100224578696600004d4d002a00000008000101120003000000010006000000000000ffe200244943435f50524f46494c450001016e6f74207265616c6c7920612070726f66696c65ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080008000801011100ffc40014000100000000000000000000000000000001ffc400171000030100000000000000000000000000001764a2ffda0008010100003f001212e4ffd9").unwrap_or([])
    match jpeg.info(b) {
        Ok(i) => print(f"{i.width}x{i.height} {i.layout}, {i.bit_depth} bits")
        Err(e) => print(f"error: {e}")
    }
    match jpeg.decode_with_meta(b) {
        Ok((img, m)) => {
            var row = ""
            for v in img.row(0) {
                row = row + f" {v}"
            }
            print(f"first row:{row}")
            print(f"{m.density_x}x{m.density_y} dpi, orientation {m.orientation}, ICC profile of {m.icc.len()} bytes")
            let shown = jpeg.apply_orientation(img, m.orientation)
            print(f"shown upright: first row {shown.row(0)[0]} {shown.row(0)[1]} ...")
        }
        Err(e) => print(f"error: {e}")
    }
    print(jpeg.orientation(b))

    // the frame header changed to SOF9, arithmetic coding
    b[164] = 0xC9u8
    match jpeg.decode(b) {
        Ok(_) => print("decoded")
        Err(e) => print(f"error: {e}")
    }
}
// output:
// 8x8 gray, 8 bits
// first row: 0 0 0 0 0 0 0 0
// 72x96 dpi, orientation 6, ICC profile of 20 bytes
// shown upright: first row 255 218 ...
// 6
// error: unsupported: arithmetic coding
```

## Functions

| Function | Result |
| --- | --- |
| `info(b: [uint8]) -> Result<ImageInfo, ImageError>` | The size and layout from the frame header, without decoding: `Gray` for one component, `Rgb` for three or four; `bit_depth` 8, `frames` 1, `format` `"jpeg"` |
| `decode(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>` | The pixels as stored, `Gray` or `Rgb` (CMYK and YCCK converted, [below](#colour)); an image of more than `max_pixels` pixels is `TooLarge` before anything is allocated |
| `decode_with_meta(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<(Image8, JpegMeta), ImageError>` | `decode`, and what the file says beside the pixels |
| `orientation(b: [uint8]) -> int` | EXIF's orientation, 1 to 8, from the markers before the first scan (nothing decoded); 1 if there is none or it is broken |
| `apply_orientation<S: Sample>(img: Image<S>, o: int) -> Image<S>` | `img` turned as orientation `o` says, so it shows upright, as Pillow's `ImageOps.exif_transpose`: 2 mirrored (`flip_h`), 3 half a turn, 4 flipped (`flip_v`), 5 `transpose`, 6 a quarter clockwise (`rotate90`), 7 transverse, 8 a quarter counter-clockwise (`rotate270`); 1 and anything else unchanged |

`decode` gives the pixels as the file stores them, as Pillow's `Image.open` does; a viewer turns them first, `apply_orientation(img, meta.orientation)` (std.imageio's `load` will do that).

```myla fragment
pub struct JpegMeta {
    jfif: bool,             // a JFIF APP0 segment
    density_unit: int,      // its unit: 0 an aspect ratio only, 1 dots per inch, 2 per centimetre
    density_x: int,
    density_y: int,
    exif: [uint8],          // APP1 "Exif": the TIFF data after "Exif\0\0", empty if none
    orientation: int,       // EXIF's 0x0112 in IFD0, 1 to 8, 1 if none
    icc: [uint8],           // APP2 "ICC_PROFILE": the chunks joined in order; empty if none or one is missing
    adobe_transform: int,   // APP14 "Adobe": 0 none (RGB, CMYK), 1 YCbCr, 2 YCCK; -1 without it
    progressive: bool,      // SOF2
    components: int,        // 1, 3 or 4, as stored
}
```

## What it reads

- **Frames:** SOF0 (baseline), SOF1 (extended sequential, Huffman tables 0 to 3) and SOF2 (progressive), 8-bit samples, 1, 3 or 4 components, sampling factors 1 to 4 that divide the largest (4:4:4, 4:2:2, 4:2:0, 4:4:0, 4:1:1 and the rest libjpeg reads), interleaved scans of up to 10 blocks an MCU and scans of one component.
- **Tables:** DQT of 8 and 16 bits; DHT, with libjpeg's checks (at most 256 codes, codes that fit their lengths, none all ones, DC symbols up to 15); libjpeg-turbo's default tables (Annex K's) where a file defines none, as Motion JPEG frames do. A component takes its quantisation table at its first scan, as libjpeg latches it.
- **Progressive scans:** spectral selection and successive approximation, DC and AC, first scans and refinements, end-of-band runs, with libjpeg's checks of each scan's band and bits.
- **Restart intervals** (DRI and RST0 to RST7), in sequential and progressive scans.
- **Markers** between segments: bytes that aren't one skipped, fill bytes, COM, DNL and the other APPn segments ignored. Every segment's length is checked against the data before it is read.
- **Not read:** arithmetic coding (SOF9 to SOF15 but SOF12), lossless JPEG (SOF3), hierarchical JPEG (SOF5 to SOF7, DHP, EXP) and 12-bit samples are `Unsupported(name)`; a frame of 2 or more than 4 components, or a height of 0 (DNL), `Unsupported` too.

A scan whose data ends early, or a file without EOI, is decoded on as if zero bits followed, as libjpeg does (it warns; Pillow then raises unless `LOAD_TRUNCATED_IMAGES`); a file cut before its first scan is `Truncated`.

## Exactness

The decoder is libjpeg's, step by step, so a JPEG decodes to the same pixels everywhere and to what Pillow (libjpeg-turbo) gives (D311, decision 7):

- the **IDCT** is jidctint.c's "islow": integers with 13 bits of fraction, two passes with 2 more bits between them, and the output through its range limit (which wraps at 1024, so a wild value gives what libjpeg gives); here in `int64`, so no input overflows;
- **upsampling** is jdsample.c's "fancy" one: the triangle filter across for 2x1 (`h2v1`), down for 1x2 (`h1v2`) and both for 2x2 (`h2v2`), each output sample 3/4 of the nearer input sample and 1/4 of the further, with libjpeg's rounding (alternately 1 and 2, or 8 and 7 in sixteenths) and the edges repeated; a component 2 samples wide or less is repeated instead, as libjpeg does, and so are the other ratios (4:1:1's 4x1);
- **colour** is jdcolor.c's fixed point: YCbCr to RGB by its four tables at 16 bits of fraction, the result clamped. A JFIF file is YCbCr; without JFIF, Adobe's transform says (0 RGB, 1 YCbCr), and without either, components named `R`, `G`, `B` are RGB.

<a id="colour"></a>Four components are CMYK (Adobe's transform 0, or no APP14) or YCCK (transform 2), stored inverted as Adobe writes them; YCCK becomes CMYK by libjpeg's conversion, and CMYK becomes RGB as Pillow's CMYK image converts: each of R, G and B is `round(C' * K' / 255)` of the stored (inverted) samples, which is `(255 - C) * (255 - K) / 255` of the uninverted ones.

The corpus of [[MYLA-945]] (`tests/burn/data/images/jpeg/`) holds every sampling factor, progressive files with spectral selection, successive approximation and restart markers, optimised tables, Adobe CMYK and EXIF orientations: each decodes to Pillow's pixels exactly, natively and `--checked`, under qemu-aarch64 and on wasm32 under Node; so do 12-megapixel baseline (4:2:0, 4:4:4) and progressive photos ([below](#speed)). Not covered by the corpus: YCCK, and a progressive file whose scans leave a coefficient not fully known, where libjpeg smooths the blocks (`do_block_smoothing`) and this decoder doesn't.

## Errors

`ImageError` ([[Language/Standard-library/Image#errors]]): `Truncated` (the data ends before the first scan, or inside a segment), `BadSignature` (no SOI), `Unsupported(name)`, `Corrupt(what)` (a bad length, table, frame or scan header, a Huffman code that isn't one, a component or table the scan names that isn't there), `TooLarge(pixels)`. Input is untrusted: every offset and index is checked, so a broken file is an `Err` or an image, never a runtime error (the fuzz runs check it, [below](#tests)).

## How it works

`Decoder.run` walks the markers from SOI and decodes each scan as it meets it. The frame header allocates every component's plane, padded to whole MCUs (and, for a progressive file, its coefficients). A sequential scan turns each block into samples at once: Huffman decoding with a table of 9 bits ahead (a code of up to 9 bits in one look, longer ones by length, as F.2.2.3), the coefficients dequantised as they are read, then `Idct.block` into the plane (a block whose AC coefficients are all zero is one value, as the full computation gives). A progressive scan adds its bits to the coefficients, which become samples after the last scan. `finish` then upsamples each component a row at a time and converts the colours.

The scans' bit buffer is std.bytes's `jpeg_reader` ([[Language/Standard-library/Bytes#jpeg]]), which undoes the 0xFF 0x00 stuffing and stops at markers; the hot loops keep its `acc` and `n` in local variables and give them back only to call `refill()` ([[Language/Standard-library/Bytes#in-a-hot-loop]]). Loading the bytes by hand in the loop instead measured no faster.

The tables an encoder needs are at the top of `lib/std/jpeg.my`, for [[MYLA-937]]: the zigzag order (`natural_order`), Annex K's quantisation tables and Huffman tables (`luma_quant`, `chroma_quant`, `std_huffman`), IJG's quality scaling (`quality_scale`, `scaled_quant`), and the colour conversion's fixed-point constants.

## Speed

Natively (`myla build`, bounds checks on), the fastest of 5 runs on the shared 4-core x86-64 machine (other work running, so runs vary by 10 %), 2026-11-25, beside Pillow 13 (libjpeg-turbo 3.2 with SIMD) on the same files, `benchmarks/images_pillow.py`'s 4000x3000 photo at quality 85:

| File | std.jpeg | Pillow | Ratio |
| --- | --- | --- | --- |
| baseline 4:2:0, 3.3 MB | 418 ms | 74 ms | 5.7 |
| baseline 4:4:4, 3.5 MB | 470 ms | 77 ms | 6.1 |
| progressive 4:2:0, 2.9 MB | 668 ms | 177 ms | 3.8 |

Where the time of the baseline 4:2:0 decode goes (phases timed with std.time): the scan about 225 ms (allocating the planes 45, Huffman decoding about 100, the IDCT about 80), then `finish` about 210 ms (allocating the output 85, upsampling 60, colour conversion 65). A third of the whole is `list.filled`, which pushes an element at a time ([[MYLA-949]]): 18 MB of planes and 36 MB of output here, and the 18 million coefficients of a progressive file (60 ms more). The progressive decode's scans take about 330 ms (their Huffman decoding about 225) and its IDCT 145.

## Tests

`lib/std/jpeg.my`'s cases pass interpreted, natively, under qemu-aarch64 and on wasm32 under Node: `#test` cases on the tables, the colour conversion, the range limit, the IDCT, EXIF's orientation in both byte orders, and `apply_orientation` for all 8 values; test functions that decode small files by Pillow (gray, 4:2:0, 4:2:2 with partial MCUs, progressive, restart markers, Adobe CMYK, an image too narrow for the triangle filter) to Pillow's pixels, read the metadata, refuse the unsupported kinds by name, and decode cuts and changed bytes to an `Err` or an image. `tests/burn/test_images.py`'s `JpegDecoder` runs `tests/burn/drivers/jpeg.my` over the corpus (exact, natively and `--checked`, the smallest files interpreted) and its fuzz cases (every truncation of the smallest files up to 512 bytes and 10,000 seeded mutations, natively plain and `--checked`): `Ok` or `Err`, never a runtime error.
