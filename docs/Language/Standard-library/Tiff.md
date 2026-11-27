# std.tiff

Baseline TIFF files, read and written ([[MYLA-965]], D313, the plan [[Project/Standard-library-roadmap/Images-vision-and-fonts]]): every page of a file, strips and tiles, both planar configurations, the compressions none, PackBits, LZW and Deflate with their predictors, 1 to 16-bit samples and 32-bit floats, bilevel, gray, RGB and palette images with an alpha sample; every tag of a page as stored. The pixels come as a [[Language/Standard-library/Image]] `Image8`, `Image16` or `ImageF`. The compression is [[Language/Standard-library/Compress]]'s.

```myla
import std.tiff as tiff
import std.image as image
from std.image import Image8, Layout

fun main() {
    // a 64x32 gradient, written with LZW and the predictor
    var img: Image8 = image.new(64, 32, Layout.Rgb, 0u8)
    for y in 0..img.height {
        for x in 0..img.width {
            img.set_color(x, y, image.rgb((x * 4) as uint8, (y * 8) as uint8, 128u8))
        }
    }
    let file = tiff.encode(img, tiff.Compression.Lzw)
    print(f"{file.len()} bytes, uncompressed {tiff.encode(img, tiff.Compression.Uncompressed).len()}")

    // what the file holds, then its pixels back
    match tiff.pages(file) {
        Ok(ps) => {
            for p in ps {
                print(f"page: {p.width}x{p.height} {p.layout}, {p.bit_depth} bits")
            }
        }
        Err(e) => print(f"error: {e}")
    }
    if let Ok(t) = tiff.tags(file, 0) {
        print(f"BitsPerSample {t[258]}, Compression {t[259]}, XResolution {t[282]}")
    }
    match tiff.decode(file) {
        Ok(back) => print(f"the same pixels: {back == img}, pixel (5, 2) {back.color_at(5, 2)}")
        Err(e) => print(f"error: {e}")
    }

    // 16 bits, and a file this module doesn't read: BigTIFF
    let deep = tiff.encode16(img.to_u16(), tiff.Compression.Deflate)
    print(f"16 bits: {tiff.decode16(deep).map((d: image.Image16) => d.data[3]).unwrap_or(0u16)}")
    var big = file
    big[2] = 43u8
    match tiff.decode(big) {
        Ok(_) => print("decoded")
        Err(e) => print(f"error: {e}")
    }
}
// output:
// 536 bytes, uncompressed 6336
// page: 64x32 rgb, 8 bits
// BitsPerSample 8, 8, 8, Compression 5, XResolution 72/1
// the same pixels: true, pixel (5, 2) #141080ff
// 16 bits: 1028
// error: unsupported: BigTIFF
```

## Functions

| Function | Result |
| --- | --- |
| `decode(b: [uint8], page: int = 0, max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>` | Page `page` (0 the first) of the file `b` at 8 bits a sample: fewer bits scaled up (`v * 255 / (2^bits - 1)`, rounded), 16 bits rounded down (`(v * 255 + 32767) / 65535`, as libpng and std.image), floats from 0..1 rounded and clamped |
| `decode16(b: [uint8], page: int = 0, max_pixels: int64 = image.MAX_PIXELS) -> Result<Image16, ImageError>` | The page at 16 bits: fewer bits scaled up (8 bits times 257), floats from 0..1 rounded and clamped |
| `decode_f32(b: [uint8], page: int = 0, max_pixels: int64 = image.MAX_PIXELS) -> Result<ImageF, ImageError>` | The page as `float32`: floats as stored, integers scaled to 0..1 |
| `pages(b: [uint8]) -> Result<[ImageInfo], ImageError>` | Every page, in order: its size, the layout the decoders give, the bits of a sample as stored (a palette's index bits, 32 for floats), `frames` 1, `format` `"tiff"`. A page the decoders can't read is an error here too |
| `info(b: [uint8]) -> Result<ImageInfo, ImageError>` | The first page as `pages` describes it, with `frames` the number of pages: counted until the chain of IFDs ends, loops back or breaks, so a broken later IFD doesn't make it fail |
| `tags(b: [uint8], page: int = 0) -> Result<[int: TagValue], ImageError>` | Every tag of the page by its number, the values as stored. A tag of a field type TIFF 6 doesn't define, or whose values lie past the end of the file, is left out; of a tag given twice, the first |
| `encode(img: Image8, compression: Compression = Compression.Lzw) -> [uint8]` | A TIFF file of `img`: one page, little endian, in strips |
| `encode16(img: Image16, compression: Compression = Compression.Lzw) -> [uint8]` | The same at 16 bits a sample |

`max_pixels` bounds what a decoder allocates: a page (or a tile) of more pixels is `TooLarge` before anything is read. A page is 0 the first; one past the last is `Mismatch("no page 3: the file has 3 pages")`.

```myla fragment
pub enum TagValue {
    Ints([int64])                  // BYTE, SHORT, LONG, SBYTE, SSHORT, SLONG, IFD (1, 3, 4, 6, 8, 9, 13), signed where the type is
    Rationals([(int64, int64)])    // RATIONAL, SRATIONAL (5, 10): numerator and denominator
    Floats([float64])              // FLOAT, DOUBLE (11, 12)
    Ascii(str)                     // ASCII (2), without the NUL that ends it (or several strings, NUL between them)
    Bytes([uint8])                 // UNDEFINED (7)
}

pub enum Compression { Uncompressed, PackBits, Lzw, Deflate }
```

`TagValue` is `Eq` and has `impl Format`: the values separated by commas, a rational as `72/1`, the first eight of a long list and how many there are (`1, 2, 3, 4, 5, 6, 7, 8, … (10 values)`), text as it is, bytes counted (`5 bytes`).

## What the decoders read

| | |
| --- | --- |
| Byte orders | `II` (little endian) and `MM` (big endian), for the structure and for samples of 16 bits and more |
| Pages | The chain of IFDs, walked with a guard: an IFD met a second time ends it (`pages` and `info` stop there; a page past it is `Mismatch`) |
| Layout of the pixels | Strips (`RowsPerStrip` missing or past the height: one strip) and tiles (the tiles at the right and bottom edges cropped); planar configuration 1 (the samples of a pixel together) and 2 (a plane a sample) |
| Compression | 1 (none), 32773 (PackBits), 5 (LZW, the old LSB-first LZW of TIFF 5.0 too), 8 and 32946 (Deflate, a zlib stream) |
| Predictors | 2 (horizontal differencing) on 8, 16 and 32-bit samples, a sample's difference to the same sample of the pixel before it, in the file's byte order; 3 (floating point, Adobe's Technical Note 3) on 32-bit floats: the bytes of a row split into planes, the most significant first, then differenced |
| Samples | Unsigned integers (`SampleFormat` 1 or 4) of 1 to 16 bits, packed from the highest bit (`FillOrder` 2 reverses each byte's bits first), and 32-bit floats (`SampleFormat` 3) |
| Photometric interpretations | 0 (WhiteIsZero, inverted), 1 (BlackIsZero), 2 (RGB), 3 (palette: `ColorMap` gives RGB, its 16-bit values' high byte at 8 bits, as Pillow, and the values as they are at 16 bits). A missing tag is 0, as Pillow reads it |
| Extra samples | The first one past the colour is alpha unless `ExtraSamples` says 0 (unspecified, then it is left out, as Pillow does); a missing `ExtraSamples` makes it unassociated alpha. Associated alpha (1) is unpremultiplied, as Pillow's `RGBa` to `RGBA` (`v * max / a`, truncated); unassociated (2) is kept. Samples after the alpha are left out |

The image is `Gray`, `GrayAlpha`, `Rgb` or `Rgba` (palette images are `Rgb`, or `Rgba` with an alpha sample).

**Out:** JPEG compression (6 and 7), CCITT RLE, G3 and G4 (2, 3, 4, 32771), JBIG, LZMA, Zstandard, WebP, JPEG 2000 and the rest are `Unsupported("JPEG compression")` and so on, a compression code it doesn't name `Unsupported("compression 99")`; BigTIFF (magic 43) is `Unsupported("BigTIFF")`; the photometric interpretations CMYK (5), YCbCr (6), CIE, ICC and ITU L\*a\*b\* (8 to 10), transparency masks (4), color filter arrays, LogL, LogLuv and LinearRaw are `Unsupported("CMYK")` and so on. Signed integer samples, floats of other sizes than 32 bits, integers of more than 16 bits, samples of different sizes within a pixel and the horizontal predictor on samples of fewer than 8 bits are `Unsupported` too.

**Untrusted input.** Every offset and count is checked against the file before it is used: an IFD outside the file is `Corrupt`, one cut short `Truncated`, a tag's values past the end are left out by `tags` and are `Truncated` where a decoder needs them; fewer strip or tile offsets than the image needs, a missing `StripByteCounts` (but for an uncompressed page, where libtiff computes it too) or a `ColorMap` of the wrong length are `Corrupt`. The size is checked against `max_pixels` (and a tile's too) before a sample is allocated, and each block is decompressed with a `max_output` of a quarter more than it needs, so a few bytes that stand for gigabytes can't take the memory: a block that holds more, or less, than its pixels is `Corrupt` or `Truncated`. A block with more data than it needs gives its first bytes (some writers pad).

## The encoder

`encode` and `encode16` write what baseline readers expect: a little-endian file of one page in strips of about 8 KB (`RowsPerStrip` 8192 bytes over a row's, at least one row, as libtiff's default), `ImageWidth`, `ImageLength`, `BitsPerSample`, `Compression`, `PhotometricInterpretation` (1 for gray, 2 for RGB), `StripOffsets`, `SamplesPerPixel`, `RowsPerStrip`, `StripByteCounts`, `XResolution` and `YResolution` (72/1), `PlanarConfiguration` 1, `ResolutionUnit` 2 (inches), `Predictor` 2 with LZW and Deflate, and `ExtraSamples` 2 (unassociated alpha) for gray and alpha or RGBA. `Compression.Lzw` (the default) and `Compression.Deflate` (zlib at level 6) use the horizontal predictor, `PackBits` compresses each row on its own (as libtiff), `Uncompressed` writes the samples as they are. An image of no pixels gives a file of no strips, which TIFF readers (this one too) refuse.

Pillow 13 reads every file `encode` and `encode16` write to the same pixels, but for 16-bit gray and alpha, a mode it doesn't have (and 16-bit RGB and RGBA, which it reads at 8 bits, the high bytes); ImageMagick 6, through libtiff, reads all of them without a warning, to the same pixels where compared (gray, RGB and RGBA; checked by hand on 300×61 images of each layout, depth and compression: 32 files).

## Speed

Natively on x86-64, the best of three runs on a 4096×4096 RGB picture (50 MB of samples: smooth gradients and a little noise), in memory, on a machine shared with other work (2026-11-25, `d784466`):

| Compression | File | `encode` | `decode` | Pillow 13's save and load (libtiff, no predictor) |
| --- | --- | --- | --- | --- |
| Uncompressed | 50.4 MB | 114 ms, 440 MB/s | 111 ms, 452 MB/s | 61 and 42 ms |
| LZW, predictor | 16.2 MB | 781 ms, 64 MB/s | 511 ms, 98 MB/s | 828 and 268 ms (45.1 MB) |
| Deflate, predictor | 14.3 MB | 3678 ms, 14 MB/s | 578 ms, 87 MB/s | 1367 and 327 ms (27.0 MB) |
| PackBits | 50.7 MB | 463 ms, 109 MB/s | 207 ms, 243 MB/s | 173 and 38 ms |

The compression is std.compress's (its own speed is on [[Language/Standard-library/Compress]]): Deflate's encoder at level 6 dominates its row. An uncompressed file whose strips lie one after the other is taken in one slice of the file; even so, copying a list natively costs about 2 ns a byte, a slice as much as a loop of `push`es ([[MYLA-951]]), which is most of the 111 ms. An 8-bit gray or RGB(A) page is the stored samples as they are; other pages go through a table a channel from each stored value to the sample (a page of fewer pixels than a sample has values converts each sample on its own, which keeps the interpreter fast on small 16-bit images).

## Tests

The module's 71 cases pass interpreted, natively, on aarch64 under qemu and on wasm32 under Node: hand-picked errors (empty and short headers, other signatures, BigTIFF in both byte orders, no IFD, an IFD outside the file or cut short, `max_pixels`, pages that aren't there, the JPEG, CCITT, CMYK and YCbCr codes, wrong sizes and offsets, more tiles than the file can hold), the helpers' vectors (both predictors in both byte orders, the bit unpacking, the type sizes and signed values, `TagValue`'s format, the encoder's exact bytes for a 2×1 image), and test functions over 17 small files made by the corpus's own TIFF writer (`tests/burn/_images_vendor.py`): strips in both byte orders, every compression, tiles with a cropped edge, planar configuration 2, 1-bit WhiteIsZero with `FillOrder` 2, 4-bit gray, a 4-bit palette, 16-bit samples with the predictor in both byte orders, floats with predictor 3 (Deflate big endian, LZW little endian), associated and unassociated alpha, `ExtraSamples` 0, three pages with tags of every field type, and an IFD that points at itself; each file is read alike by Pillow, but for the big-endian floats with predictor 3, which Pillow 13 misreads (it swaps the bytes libtiff's predictor already made native; libtiff itself, through ImageMagick, reads the samples written, and so does this module). Every layout and compression goes through `encode` and `encode16` and back, and a 300×30 image in several strips.

`tests/burn/test_images.py` runs three drivers over the corpus's TIFF folder (`tests/burn/data/images/tiff/`, 41 files: Pillow's decode of each is the expected pixels): `tiff` (`decode` of page 0; it calls `pages`, `info` and `tags` on each input too), `tiff16_last_page` (`decode16` of the last page `pages` finds: the multi-page file's 16-bit third page) and `tiff_f32` (`decode_f32` of the float files), each natively, `--checked` and in the interpreter on its smallest files, and fuzzed: every truncation of the six smallest files up to 512 bytes and 10,000 seeded mutations of all of them, plain and `--checked`, each `Ok` or `Err` and never a runtime error (also 30,000 mutations with each of three other seeds).
