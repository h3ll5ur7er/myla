# std.pnm

The Netpbm formats ([[MYLA-960]], the plan [[Project/Standard-library-roadmap/Images-vision-and-fonts]]): PBM (bilevel), PGM (gray) and PPM (RGB), each in its plain (ASCII) and its binary form, and PAM with every tuple type of one to four channels, at any MAXVAL from 1 to 65535. They are the simplest image files there are, a short text header and the samples as they are, so the image tests write their expected pixels in PAM, and any program can read or write them with no library at all. Images are [[Language/Standard-library/Image]]'s.

```myla
import std.image as image
from std.image import Image8, Layout
import std.pnm as pnm
from std.pnm import Kind
import std.bytes as bytes

fun main() {
    // a 3x2 picture written as plain PPM, which is text
    var img: Image8 = image.new(3, 2, Layout.Rgb, 0u8)
    img.set_color(0, 0, image.rgb(255u8, 0u8, 0u8))
    img.set_color(2, 1, image.rgb(0u8, 128u8, 255u8))
    let text = pnm.encode_as(img, Kind.Ppm, true)
    for line in bytes.to_str(text).split("\n") {
        if line.len() > 0 {
            print(line)
        }
    }
    // read back, and the binary form of the same
    print(pnm.decode(text, image.MAX_PIXELS).unwrap_or(img) == img)
    let binary = pnm.encode(img)
    print(f"{binary.len()} bytes, {bytes.to_str(binary[:2])}")

    // a 16-bit gray file with MAXVAL 1000: decode16 scales it to 0..65535
    let deep = bytes.from_str("P5\n2 1\n1000\n").concat([0u8, 250u8, 3u8, 232u8])
    if let Ok(i) = pnm.info(deep) {
        print(f"{i.width}x{i.height} {i.layout}, {i.bit_depth} bits")
    }
    if let Ok(g) = pnm.decode16(deep, image.MAX_PIXELS) {
        print(f"{g.data[0]} {g.data[1]}")
    }
    match pnm.decode(bytes.from_str("P6\n1 1\n255\n"), image.MAX_PIXELS) {
        Ok(_) => print("decoded")
        Err(e) => print(f"{e}")
    }
}
// output:
// P3
// 3 2
// 255
// 255 0 0 0 0 0 0 0 0
// 0 0 0 0 0 0 0 128 255
// true
// 29 bytes, P6
// 2x1 gray, 10 bits
// 16384 65535
// truncated input
```

## Functions

| Function | Result |
| --- | --- |
| `info(b: [uint8]) -> Result<ImageInfo, ImageError>` | What the header says: size, layout, `bit_depth` the bits MAXVAL needs (1 for PBM, 8 for 255, 16 for 65535), one frame, `format` `"pnm"` |
| `decode(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>` | The image at 8 bits a sample |
| `decode16(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image16, ImageError>` | The image at 16 bits a sample |
| `encode(img: Image8) -> [uint8]` | The binary file of the image's own kind: PGM (P5) for `Gray`, PPM (P6) for `Rgb`, PAM (P7) for a layout with alpha; MAXVAL 255 |
| `encode_as(img: Image8, kind: Kind, ascii: bool = false) -> [uint8]` | The image as `kind`, plain if `ascii` |
| `encode16(img: Image16) -> [uint8]`, `encode16_as(img: Image16, kind: Kind, ascii: bool = false) -> [uint8]` | The same at MAXVAL 65535, two bytes big endian a sample |

`enum Kind { Pbm, Pgm, Ppm, Pam }` is what `encode_as` writes. PGM and PPM convert the image to gray (BT.601 luma, [[Language/Standard-library/Image#layouts-and-sample-types]]) or to RGB, dropping alpha. PBM writes the gray of each pixel thresholded: a sample below half scale (128, or 32768 at 16 bits) is black. PAM keeps the layout, with the tuple type `GRAYSCALE`, `GRAYSCALE_ALPHA`, `RGB` or `RGB_ALPHA`; it has no plain form, so `ascii` is ignored for it. A plain file has a row of the image a line, no line longer than 70 bytes, as Netpbm writes them.

## Reading

`decode` and `decode16` read all seven forms, P1 to P7. A header is whitespace-separated decimal numbers with `#` comments to the end of a line anywhere between them; a binary raster starts after the one whitespace byte that follows the last number. A PAM header is lines of a keyword and its value (`WIDTH`, `HEIGHT`, `DEPTH`, `MAXVAL`, `TUPLTYPE`, repeated `TUPLTYPE`s joined by a space) up to `ENDHDR`; an unknown keyword is `Corrupt`. The layout is the tuple type's: `BLACKANDWHITE` and `GRAYSCALE` gray, `BLACKANDWHITE_ALPHA` and `GRAYSCALE_ALPHA` gray and alpha, `RGB`, `RGB_ALPHA`; a known type with the wrong `DEPTH` is `Corrupt`, and an unknown one (or none) is read by its depth, 1 to 4 (more is `Unsupported`). Bytes after the image are ignored.

A sample scales to the full range of the result, rounded half up: `v * 255 / maxval` for `decode` and `v * 65535 / maxval` for `decode16`. A MAXVAL past 255 has two bytes a sample in the binary forms; `decode` reads such a file at 16 bits first and rounds that to 8 as `to_unorm8` does, so a 16-bit file gives the same through `decode` as through `decode16` and `to_u8()`. These are the values Pillow gives for every file of the corpus. PBM's 1 is black, so it decodes to 0 and its 0 to full scale; PAM's `BLACKANDWHITE` keeps its numbers' meaning, 1 white.

A plain raster's sample above MAXVAL is `Corrupt`, as is anything but digits, whitespace and comments in it; a binary raster's is clamped to full scale (it can't be checked without a pass of its own, and Pillow clamps too). A raster that ends early is `Truncated`, a MAXVAL of 0 or past 65535 `Corrupt`, a magic other than P1 to P7 `BadSignature`. A header that asks for more than `max_pixels` pixels is `TooLarge` before anything is allocated.

## Speed

Natively (`myla build`, a shared 4-core x86-64 machine, 2026-11-25), the best of three runs on a 4096×4096 RGB image (50 MB): `encode` (P6) 108 to 110 ms and `decode` 114 to 116 ms, about 450 MB a second. Both are a copy of the samples behind the header, and most of the time is making the 50 MB list. Decoding another MAXVAL goes through a table of every raw value, and the plain forms parse a number a sample.

## Tests

The module's 43 cases pass interpreted, natively and on wasm32 under Node: `#test` cases on every public function and the helpers, and test functions for every kind in both forms round-tripping at 8 and 16 bits, the exact bytes written, the 70-byte lines, comments, PAM's tuple types and the errors. The corpus (`tests/burn/data/images/pnm/`: every kind, MAXVALs 15 and 1000, 16 bits, broken files) decodes to Pillow's pixels through `decode` and `decode16` (`tests.burn.test_images`' `PnmDecoder` and `Pnm16Decoder`), natively, `--checked` and interpreted, and its truncations and 10,000 seeded mutations are `Ok` or `Err`, never a runtime error. `tests.burn.test_simple_images` writes every file of the three simple formats in every kind and form, reads it back, and has Pillow read the PBM, PGM and PPM files.
