# std.png

PNG images read and written ([[MYLA-961]], D313, the plan [[Project/Standard-library-roadmap/Images-vision-and-fonts]]): every colour type and bit depth, transparency, interlacing and the five filters on the way in, with every chunk's CRC checked; adaptive filtering, zlib at any level and the smallest lossless colour type on the way out. Its images are std.image's ([[Language/Standard-library/Image]]); the compression is std.compress's ([[Language/Standard-library/Compress]]).

```myla
import std.png as png
import std.image as image
from std.image import Layout, Indexed
from std.png import Filter

fun main() {
    // a 3x2 image: a gray ramp, all of it opaque
    var img = image.new(3, 2, Layout.Rgba, 255u8)
    for x in 0..3 {
        for y in 0..2 {
            img.set_color(x, y, image.rgb((x * 100) as uint8, (x * 100) as uint8, (x * 100) as uint8))
        }
    }
    let b = png.encode(img, 9, Filter.Adaptive)
    // gray and opaque: written as 8-bit gray, one sample a pixel
    if let Ok(i) = png.info(b) {
        print(f"{b.len()} bytes: {i.width}x{i.height} {i.layout}, {i.bit_depth} bits")
    }
    // decoded as written; `img` widened to RGBA again compares equal
    if let Ok(back) = png.decode(b) {
        print(f"{back.layout} {back.data[1]} {back.data[2]}, the same: {back.convert(Layout.Rgba) == img}")
    }
    if let Ok(wide) = png.decode16(b) {
        print(f"16 bits: {wide.data[1]}")
    }

    // a palette image: two colours, one of them half transparent
    let ix = Indexed { width: 4, height: 1, palette: [image.rgb(255u8, 0u8, 0u8), image.rgba(0u8, 0u8, 255u8, 128u8)], indices: [0u8, 1u8, 1u8, 0u8] }
    let p = png.encode_indexed(ix)
    if let Ok(i) = png.info(p) {
        print(f"palette: {i.layout}, {i.bit_depth} bit a pixel")
    }

    // a byte of the header changed: its CRC doesn't match
    var bad = b
    bad[18] = 9u8
    match png.decode(bad) {
        Ok(_) => print("decoded")
        Err(e) => print(f"error: {e}")
    }
}
// output:
// 73 bytes: 3x2 gray, 8 bits
// gray 100 200, the same: true
// 16 bits: 25700
// palette: rgba, 1 bit a pixel
// error: checksum mismatch
```

## Functions

```myla fragment
pub fun info(b: [uint8]) -> Result<ImageInfo, ImageError>
pub fun decode(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>
pub fun decode16(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image16, ImageError>
pub fun decode_with_meta(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<(Image8, PngMeta), ImageError>
pub fun encode(img: Image8, level: int = 6, filter: Filter = Filter.Adaptive) -> [uint8]
pub fun encode16(img: Image16, level: int = 6, filter: Filter = Filter.Adaptive) -> [uint8]
pub fun encode_indexed(ix: image.Indexed, level: int = 6) -> [uint8]
```

| Function | Result |
| --- | --- |
| `info(b)` | The size, the layout `decode` gives and the bit depth as stored (1 to 16), read from the chunks before the image data, whose CRCs are checked; `frames` is 1, `format` `"png"` |
| `decode(b, max_pixels)` | The image with 8-bit samples: 16-bit ones rounded as libpng and std.image round them (`(v * 255 + 32767) / 65535`) |
| `decode16(b, max_pixels)` | The image with 16-bit samples: 8 bits and fewer widened by 257 (after scaling to 8) |
| `decode_with_meta(b, max_pixels)` | `decode`'s image and the file's `PngMeta` |
| `encode(img, level, filter)` | The PNG of `img`, compressed at `level` (0 to 9, zlib's; outside that, as `zlib_compress` takes it) |
| `encode16(img, level, filter)` | The same at 16 bits a sample |
| `encode_indexed(ix, level)` | A palette image: `PLTE`, `tRNS` up to the last colour that isn't opaque, the indices at 1, 2, 4 or 8 bits, whichever is the smallest that holds them, unfiltered (as libpng advises for palettes) |

The encoders panic on an image of no pixels (PNG has none), on samples that don't fill the image, and `encode_indexed` on a palette of more than 256 colours. An index past the palette is written as transparent black, which is what `ix.to_image()` makes of it.

## Decoding

- **Colour types and depths.** Gray at 1, 2, 4, 8 and 16 bits, RGB, gray and alpha, and RGBA at 8 and 16, and palettes at 1, 2, 4 and 8. Gray of fewer than 8 bits is scaled to 8 as libpng does: `v * 255 / (2^d - 1)`, so 2-bit gray is 0, 85, 170 or 255.
- **Layouts.** Gray, gray and alpha, RGB and RGBA come as `Gray`, `GrayAlpha`, `Rgb` and `Rgba`. A palette image is `Rgb`, or `Rgba` if it has a `tRNS` (colours past the `tRNS` are opaque, an index past the palette black). Gray or RGB with a `tRNS` colour key is `GrayAlpha` or `Rgba`: alpha 0 where the pixel is the key (compared at the depth stored, before scaling), full elsewhere. A `tRNS` of the wrong length, or one longer than the palette, is ignored, as libpng ignores it.
- **Interlacing and filters.** Adam7's seven passes are put back in place; each row's filter (none, Sub, Up, Average, Paeth) is undone. Any other filter type is `Corrupt`.
- **Checks.** The signature (`BadSignature`, or `Truncated` for an input that ends inside it), every chunk's CRC-32 (`Checksum`), IHDR first and well formed (sizes from 1 to 2^31 − 1, a colour type and depth PNG allows, methods 0), a `PLTE` for a palette image, at least one IDAT. An unknown critical chunk is `Unsupported`; an unknown ancillary chunk is skipped. The image data, every IDAT's bytes one after the other, must be one zlib stream (its Adler-32 checked) of exactly the bytes the header calls for: a stream cut short is `Truncated`, one that gives fewer bytes or more is `Corrupt`. A missing IEND is forgiven when the image data is whole.
- **Limits.** `max_pixels` (2^28 by default) is checked when IHDR is read, before anything is allocated: past it is `TooLarge` with the pixels asked for. The inflater is given the exact size the header claims as its limit, so a small file can't expand to more than its image; an image whose data would be more than 2^31 − 1 bytes is `TooLarge` too.

## Metadata

```myla fragment
pub struct PngMeta {
    gamma: Option<int64>,      // gAMA: the gamma times 100000 (45455 for 1 / 2.2)
    srgb: Option<int>,         // sRGB: the rendering intent, 0 to 3
    icc_name: str,             // iCCP: the profile's name ("" without one)
    icc_profile: [uint8],      // iCCP: the profile, decompressed, not applied
    phys: Option<Phys>,        // pHYs
    text: [TextChunk],         // tEXt, zTXt and iTXt, in file order
}
pub struct Phys { x: int64, y: int64, meter: bool }   // pixels per unit; the metre, or unknown (an aspect ratio)
pub struct TextChunk { keyword: str, text: str, language: str, translated: str, compressed: bool }
```

`decode_with_meta` keeps these; none of them changes the pixels. `tEXt` and `zTXt` are Latin-1, given here as UTF-8; `iTXt` is UTF-8 with a language tag and a translated keyword. The first `gAMA`, `sRGB`, `iCCP` and `pHYs` count. A malformed one (a wrong length, a keyword of 0 or more than 79 bytes, a compressed part that isn't zlib, more than 16 MiB inflated, an `iTXt` that isn't UTF-8) is left out, as libpng leaves it out; its CRC is checked all the same.

## Encoding

```myla fragment
pub enum Filter { NoFilter, Sub, Up, Average, Paeth, Adaptive }
```

`Adaptive` filters each row by the filter whose output has the smallest sum of absolute values, each byte read as a signed one: libpng's heuristic. The others filter every row the same way. The rows go through std.compress's `zlib_compress(level)`, in IDAT chunks of up to 64 KiB.

The colour type is the smallest that loses nothing: gray if every pixel's red, green and blue are equal, no alpha if every alpha is full. So a `decode` of an `encode` gives the same samples, in that smaller layout when it applied; `img.convert(layout)` brings it back. `encode16` keeps 16 bits even when they would fit 8.

## Speed

Natively, on the shared 4-core x86-64 machine of 2026-11-25, the 12-megapixel picture of `benchmarks/images_std.my` (a photo-like RGB image):

| Work | std.png | Pillow 13 (libpng, zlib-ng) |
| --- | --- | --- |
| Decode | 400 ms (inflate 255 ms, chunks and CRC 60 ms, unfiltering about 85 ms) | 196 ms |
| Encode, level 6, adaptive | 5.2 s (deflate 4.7 s, choosing and applying filters 0.48 s) | 3.1 s |
| File size | 13.66 MB | 14.7 MB |

Most of the time is std.compress's: the PNG side is the unfiltering (in place in the inflated data, an 8-bit image's samples are that list itself) and the filter choice, whose Paeth predictor is computed without branches.

## Not yet

APNG (`acTL`, `fcTL`, `fdAT`: the first frame is what `decode` gives), writing metadata chunks, lower bit depths for gray (a gray image whose levels fit 4 bits is written at 8), and colour management (`gAMA` and `iCCP` are kept, not applied).
