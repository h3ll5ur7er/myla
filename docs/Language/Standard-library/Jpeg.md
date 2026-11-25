# std.jpeg

JPEG decoding ([[MYLA-936]], D311, the plan [[Project/Standard-library-roadmap/Images-vision-and-fonts]]): baseline, extended sequential and progressive JPEG, Huffman coded, 8 bits a sample, gray, YCbCr, RGB and Adobe's CMYK and YCCK, every sampling factor libjpeg reads, restart intervals, and the metadata beside the pixels (JFIF's density, EXIF and its orientation, the ICC profile). It decodes to the same pixels as libjpeg with its defaults, bit for bit, so to what Pillow gives, on every target. And baseline encoding ([[MYLA-937]], [below](#encoding)): a JFIF file at a quality of 1 to 100 with the chroma at 4:4:4, 4:2:2 or 4:2:0, byte for byte the file libjpeg (Pillow) writes with the same settings. Images are std.image's ([[Language/Standard-library/Image]]).

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
| `decode(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>` | The pixels as stored, `Gray` or `Rgb` (CMYK and YCCK converted, [below](#cmyk-and-ycck)); an image of more than `max_pixels` pixels is `TooLarge` before anything is allocated |
| `decode_with_meta(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<(Image8, JpegMeta), ImageError>` | `decode`, and what the file says beside the pixels |
| `orientation(b: [uint8]) -> int` | EXIF's orientation, 1 to 8, from the markers before the first scan (nothing decoded); 1 if there is none or it is broken |
| `apply_orientation<S: Sample>(img: Image<S>, o: int) -> Image<S>` | `img` turned as orientation `o` says, so it shows upright, as Pillow's `ImageOps.exif_transpose`: 2 mirrored (`flip_h`), 3 half a turn, 4 flipped (`flip_v`), 5 `transpose`, 6 a quarter clockwise (`rotate90`), 7 transverse, 8 a quarter counter-clockwise (`rotate270`); 1 and anything else unchanged |
| `encode(img: Image8, quality: int = 85, subsampling: Subsampling = Subsampling.S420) -> [uint8]` | `img` as a baseline JFIF file ([Encoding](#encoding)): gray and gray + alpha as one component, RGB and RGBA as YCbCr with the chroma sampled as `subsampling` says, alpha dropped; `quality` clamped to 1 to 100. No bytes (`[]`) for an image JPEG can't hold, with a side of 0 or more than 65,535, or whose `data` doesn't fit its size |

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

The corpus of [[MYLA-945]] (`tests/burn/data/images/jpeg/`) holds every sampling factor, progressive files with spectral selection, successive approximation and restart markers, optimised tables, Adobe CMYK and EXIF orientations: each decodes to Pillow's pixels exactly, natively and `--checked`, under qemu-aarch64 and on wasm32 under Node; so do 12-megapixel baseline (4:2:0, 4:4:4) and progressive photos ([below](#speed)). Not covered by the corpus: YCCK, and a progressive file whose scans leave a coefficient not fully known, where libjpeg smooths the blocks (`do_block_smoothing`) and this decoder doesn't.

### CMYK and YCCK

Four components are CMYK (Adobe's transform 0, or no APP14) or YCCK (transform 2, or any other, as libjpeg assumes), stored inverted as Adobe writes them; YCCK becomes CMYK by libjpeg's conversion, and CMYK becomes RGB as Pillow's CMYK image converts: each of R, G and B is `round(C' * K' / 255)` of the stored (inverted) samples, which is `(255 - C) * (255 - K) / 255` of the uninverted ones.

## Errors

`ImageError` ([[Language/Standard-library/Image#Errors]]): `Truncated` (the data ends before the first scan, or inside a segment), `BadSignature` (no SOI), `Unsupported(name)`, `Corrupt(what)` (a bad length, table, frame or scan header, a Huffman code that isn't one, a component or table the scan names that isn't there), `TooLarge(pixels)`. Input is untrusted: every offset and index is checked, so a broken file is an `Err` or an image, never a runtime error (the fuzz runs check it, [below](#tests)).

## How it works

`Decoder.run` walks the markers from SOI and decodes each scan as it meets it. The frame header allocates every component's plane, padded to whole MCUs (and, for a progressive file, its coefficients). A sequential scan turns each block into samples at once: Huffman decoding with a table of 9 bits ahead (a code of up to 9 bits in one look, longer ones by length, as F.2.2.3), the coefficients dequantised as they are read, then `Idct.block` into the plane (a block whose AC coefficients are all zero is one value, as the full computation gives). A progressive scan adds its bits to the coefficients, which become samples after the last scan. `finish` then upsamples each component a row at a time and converts the colours.

The scans' bit buffer is std.bytes's `jpeg_reader` ([[Language/Standard-library/Bytes#JPEG]]), which undoes the 0xFF 0x00 stuffing and stops at markers; the hot loops keep its `acc` and `n` in local variables and give them back only to call `refill()` ([[Language/Standard-library/Bytes#In a hot loop]]). Loading the bytes by hand in the loop instead measured no faster.

The tables the encoder shares are at the top of `lib/std/jpeg.my`: the zigzag order (`natural_order`), Annex K's quantisation tables and Huffman tables (`luma_quant`, `chroma_quant`, `std_huffman`), IJG's quality scaling (`quality_scale`, `scaled_quant`), and the colour conversion's fixed-point constants.

## Speed

Natively (`myla build`, bounds checks on), the fastest of 5 runs, over several runs on the shared 4-core x86-64 machine (other work running, so runs vary by 10 to 15 %), 2026-11-25, beside Pillow 13 (libjpeg-turbo 3.2 with SIMD) on the same files: `benchmarks/images_pillow.py`'s 4000x3000 photo saved by Pillow at quality 85 (`benchmarks/images_std.my` times a JPEG file given as an argument):

| File | std.jpeg | Pillow | Ratio |
| --- | --- | --- | --- |
| baseline 4:2:0, 3.3 MB | 400 to 430 ms | 74 ms | 5.5 |
| baseline 4:4:4, 3.5 MB | 465 to 500 ms | 77 ms | 6.2 |
| progressive 4:2:0, 2.9 MB | 650 to 780 ms | 177 ms | 3.9 |

Where the time of the baseline 4:2:0 decode goes (phases timed with std.time): the scan about 225 ms (allocating the planes 45, Huffman decoding about 100, the IDCT about 80), then `finish` about 210 ms (allocating the output 85, upsampling 60, colour conversion 65). A third of the whole is `list.filled`, which pushes an element at a time ([[MYLA-949]]): 18 MB of planes and 36 MB of output here, and the 18 million coefficients of a progressive file (60 ms more). The progressive decode's scans take about 330 ms (their Huffman decoding about 225) and its IDCT 145.

## Tests

`lib/std/jpeg.my`'s cases pass interpreted, natively, under qemu-aarch64 and on wasm32 under Node: `#test` cases on the tables, the colour conversion, the range limit, the IDCT, EXIF's orientation in both byte orders, and `apply_orientation` for all 8 values; test functions that decode small files by Pillow (gray, 4:2:0, 4:2:2 with partial MCUs, progressive, restart markers, Adobe CMYK, an image too narrow for the triangle filter) to Pillow's pixels, read the metadata, refuse the unsupported kinds by name, and decode cuts and changed bytes to an `Err` or an image. `tests/burn/test_images.py`'s `JpegDecoder` runs `tests/burn/drivers/jpeg.my` over the corpus (exact, natively and `--checked`, the smallest files interpreted) and its fuzz cases (every truncation of the smallest files up to 512 bytes and 10,000 seeded mutations, natively plain and `--checked`): `Ok` or `Err`, never a runtime error.

## Encoding

```myla
import std.jpeg as jpeg
from std.jpeg import Subsampling
import std.image as image
from std.image import Layout
import std.imgproc as imgproc

fun main() {
    // a 24x16 picture: red rising to the right, blue downwards
    var img = image.new(24, 16, Layout.Rgb, 80u8)
    for y in 0..16 {
        for x in 0..24 {
            img[(x, y, 0)] = (x * 10) as uint8
            img[(x, y, 2)] = (y * 15) as uint8
        }
    }
    for s in [Subsampling.S444, Subsampling.S420] {
        let b = jpeg.encode(img, 90, s)
        let back = jpeg.decode(b).unwrap_or(img)
        let p = imgproc.psnr(img, back).unwrap_or(0.0)
        let name = if s == Subsampling.S444 { "4:4:4" } else { "4:2:0" }
        print(f"quality 90, {name}: {b.len()} bytes, PSNR {p:.1} dB")
    }
    // gray (and gray + alpha) is one component; quality 85, 4:2:0 by default
    let g = jpeg.encode(img.convert(Layout.Gray))
    match jpeg.info(g) {
        Ok(i) => print(f"{g.len()} bytes: {i.width}x{i.height} {i.layout}")
        Err(e) => print(f"error: {e}")
    }
    // what JPEG can't hold gives no bytes
    print(jpeg.encode(image.new(70000, 1, Layout.Gray, 0u8)).len())
}
// output:
// quality 90, 4:4:4: 731 bytes, PSNR 46.3 dB
// quality 90, 4:2:0: 696 bytes, PSNR 40.4 dB
// 364 bytes: 24x16 gray
// 0
```

```myla fragment
#derive(Eq)
pub enum Subsampling {
    S444    // Cb and Cr at every pixel
    S422    // at every other column (the MCU 16x8)
    S420    // at every other column of every other row (16x16)
}
```

`encode` writes what libjpeg writes with its defaults and Pillow's settings (`Image.save(f, "JPEG", quality=q, subsampling=s)`, `optimize` off, not progressive): SOI; a JFIF APP0 of version 1.01 with no unit and a 1:1 density; a DQT for each quantisation table, Annex K's luminance table (and for colour the chrominance one) scaled by IJG's formula for `quality` (`scaled_quant`, each value 1 to 255); SOF0 with the components 1, 2 and 3 (Y sampled 1x1, 2x1 or 2x2, Cb and Cr 1x1); a DHT for each of Annex K's standard Huffman tables it uses; one interleaved scan (one component for gray), no restart markers; EOI. The file is the same as Pillow's byte for byte, the JFIF density aside when Pillow is given a `dpi` (tested: [below](#tests-of-the-encoder)). Pillow's default quality is 75, `encode`'s 85; Pillow writes a gray image's sampling factors as its `subsampling` says, which changes no other byte, and `encode` always writes 1x1.

Step by step, each as libjpeg-turbo does it:

- **colour** (jccolor.c): RGB to YCbCr in fixed point with 16 bits of fraction, `Y = (19595 R + 38470 G + 7471 B + 32768) >> 16`, Cb and Cr rounded with a half less one (`(32768 B - 11059 R - 21709 G + (128 << 16) + 32767) >> 16`), so 255 can't round up to 256. Gray is taken as it is; alpha is dropped (Pillow refuses to write it).
- **edges** (jcprepct.c, jcsample.c): the image's last column is repeated out to whole blocks, and its last row to a whole row group (2 rows at 4:2:0); below that the last row of each component, *after* downsampling, is repeated to the bottom of the MCU row. A partial MCU's blocks wholly outside the image are dummies (jccoefct.c): AC zero and the DC of the block before.
- **downsampling** (jcsample.c, smoothing off as Pillow leaves it): each Cb or Cr sample the mean of its 2 (4:2:2, `h2v1`) or 4 (4:2:0, `h2v2`) pixels, rounded with a bias that alternates along the row, 0 and 1 halves or 1 and 2 quarters, so the roundings even out.
- **DCT** (jfdctint.c): the "islow" forward DCT, 13 bits of fraction, rows then columns with 2 bits more between them, the result 8 times the true DCT's; in `int` (it can't overflow for 8-bit samples).
- **quantisation** (jcdctmgr.c): libjpeg-turbo divides by 8q with a reciprocal, `((|x| + c) * f) >> r` with its `compute_reciprocal`'s `f`, `c` and `r` (`reciprocal`), the sign put back after. For 8-bit samples that is exactly `(|x| + 4q) / 8q` (a half rounded away from zero; checked for every q from 1 to 255 and every |x| up to 8200), here by the same multiplication, which is faster than the division. A coefficient below the smallest magnitude that gives 1 is 0 without it.
- **Huffman coding** (jchuff.c): the DC's difference from the component's previous one, the AC coefficients as runs of zeros with ZRL and EOB, each 0xFF byte followed by 0x00, the last byte filled with 1 bits.

The encoder works an MCU row at a time: the row's pixels converted into full-resolution strips (16 rows at 4:2:0, 8 otherwise), the chroma downsampled into strips of its own, then each MCU's blocks transformed, quantised and coded at once. The bit buffer is in local variables while a block is coded, and whole bytes go out when it holds 32 bits ([[Language/Standard-library/Bytes#In a hot loop]] says why not `jpeg_writer`).

### Speed of the encoder

Natively (`myla build`, bounds checks on), the fastest of 5 runs on the shared 4-core x86-64 machine, 2026-11-25, beside Pillow 13 (libjpeg-turbo 3.2 with SIMD) on `benchmarks/images_pillow.py`'s 4000x3000 picture, quality 85 (`benchmarks/images_std.my`):

| Subsampling | std.jpeg | Pillow | Ratio | File (both) |
| --- | --- | --- | --- | --- |
| 4:2:0 | 300 to 310 ms | 45 ms | 6.8 | 3,278,764 bytes |
| 4:4:4 | 410 to 430 ms | 59 ms | 7.1 | 3,467,440 bytes |

Where the 4:2:0 encode's time goes (counted with callgrind): the DCT about 40 %, the colour conversion and downsampling 30 %, quantisation and Huffman coding 25 %. Fusing quantisation with the Huffman coding and skipping the coefficients that quantise to zero took it from 495 ms to 309 ms. Every sample, coefficient and table access is a bounds-checked list access, where libjpeg-turbo's SIMD code does 8 or 16 at once.

### Tests of the encoder

`lib/std/jpeg.my`'s cases (interpreted and native): `#test` cases on the colour conversion, the reciprocals and the quantisation, the Huffman code assignment and the forward DCT; test functions that encode small images (4:4:4, 4:2:2 and 4:2:0, gray, RGBA, gray + alpha, 1x1, partial MCUs with dummy blocks, qualities 1 and 100) to the bytes Pillow writes for them, every quality from -5 to 101 to a file the decoder reads, and refuse what JPEG can't hold. `tests/burn/test_jpeg_encode.py` runs `tests/burn/drivers/jpeg_encode.my` over 1,053 cases: every 8-bit still image of the corpus with its pixels at quality 75 in each subsampling, its photo-like JPEG images at qualities 50, 75, 90 and 95, a colour and a gray image at every quality from 1 to 100, generated images of 15 odd sizes (1x1 to 40x1) in all four layouts, and the 12-megapixel picture at quality 85 in each subsampling and at 50 to 95 in 4:2:0. Every file is Pillow's byte for byte (its size and SHA-256 are vendored in `tests/burn/data/jpeg_encode.json`, so CI needs no Pillow; `--vendor` makes them again), and its PSNR and size are those of Pillow's file (the task asked for within 0.5 dB and 10 %). Some run again built `--checked` and in the interpreter. With Pillow installed, Pillow decodes every file to the samples std.jpeg decodes, its encoder is asked again, and 300 random images of random sizes, layouts, qualities and subsamplings must come out as Pillow writes them.
