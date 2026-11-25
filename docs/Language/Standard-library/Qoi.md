# std.qoi

The Quite OK Image format ([[MYLA-934]], the plan [[Project/Standard-library-roadmap/Images-vision-and-fonts]]): lossless RGB and RGBA in a format whose whole specification ([qoiformat.org](https://qoiformat.org/qoi-specification.pdf), version 1.0) is a page. Its files are larger than PNG's but much quicker to write and read: for output when PNG's size doesn't matter. Images are [[Language/Standard-library/Image]]'s.

```myla
import std.image as image
from std.image import Image8, Layout
import std.qoi as qoi

fun main() {
    // a 64x64 RGBA image: flat areas and a gradient compress well
    var img: Image8 = image.new(64, 64, Layout.Rgba, 0u8)
    for y in 0..64 {
        for x in 0..64 {
            let c = if x < 32 { image.rgba(200u8, 30u8, 30u8, 255u8) } else { image.rgba((x * 4) as uint8, 100u8, (y * 4) as uint8, 200u8) }
            img.set_color(x, y, c)
        }
    }
    let file = qoi.encode(img)
    print(f"{img.data.len()} bytes of samples in {file.len()}")
    print(qoi.decode(file, image.MAX_PIXELS).unwrap_or(img) == img)
    if let Ok(i) = qoi.info(file) {
        print(f"{i.width}x{i.height} {i.layout}")
    }
    match qoi.decode(file[:100], image.MAX_PIXELS) {
        Ok(_) => print("decoded")
        Err(e) => print(f"{e}")
    }
}
// output:
// 16384 bytes of samples in 4441
// true
// 64x64 rgba
// truncated input
```

## Functions

| Function | Result |
| --- | --- |
| `info(b: [uint8]) -> Result<ImageInfo, ImageError>` | What the 14-byte header says: size, `Rgb` (3 channels) or `Rgba` (4), 8 bits, one frame, `format` `"qoi"` |
| `decode(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>` | The image, `Rgb` or `Rgba` as the header says |
| `encode(img: Image8) -> [uint8]` | The image as a QOI file: 3 channels for `Gray` (written as RGB) and `Rgb`, 4 for a layout with alpha; colour space 0 (sRGB with linear alpha) |

## The format

After the header (`qoif`, width and height as 32-bit big-endian numbers, channels, colour space) each pixel is one of: a run of 1 to 62 copies of the pixel before, an entry of a table of 64 colours seen recently (by a hash of the colour), a difference of -2 to 1 from the pixel before in each of red, green and blue, a "luma" difference (green -32 to 31, red and blue -8 to 7 relative to green's), or the colour itself, as RGB or RGBA. The pixel before the first is opaque black, and the arithmetic wraps around 256. Eight bytes, seven zeros and a one, end the file.

`encode` makes the reference encoder's (`qoi.h`) choices, so it writes the same bytes: the QOI files of the corpus, which Pillow wrote, come back byte for byte but for the colour space byte (Pillow writes 1). `decode` doesn't insist on the end marker, and reads the colour space only to check it is 0 or 1. Data that ends before the last pixel is `Truncated`, channels other than 3 and 4 or a colour space past 1 `Corrupt`, a magic other than `qoif` `BadSignature`. A header that asks for more than `max_pixels` pixels is `TooLarge` before anything is allocated.

## Speed

Natively (`myla build`, a shared 4-core x86-64 machine, 2026-11-25), the best of three runs on a 4096×4096 RGB picture of gradients with noise and flat bands (50 MB of samples, 23.6 MB as QOI): `encode` 259 to 298 ms (about 60 megapixels a second), `decode` 337 to 363 ms (about 48 megapixels a second), of which some 100 ms is making the 50 MB list. The loops keep the pixel before in local variables and the table as 64 packed `uint32`s (red, green, blue and alpha), which took encoding from 425 ms down; reading the samples into a list made up front or a push at a time costs the same.

## Tests

The module's 12 cases pass interpreted, natively and on wasm32 under Node: `#test` cases on `info`, `encode` and `decode` with every operation, and test functions for Pillow's encoding of a 70-pixel row (a run of 62 and one, a difference, colours as they are, the table, an alpha change) read and written back byte for byte, pseudo-random RGB, RGBA and gray images round-tripping, runs to the end, an empty image, every truncation and the errors. The corpus (`tests/burn/data/images/qoi/`) decodes to Pillow's pixels (`tests.burn.test_images`' `QoiDecoder`), natively, `--checked` and interpreted, and its truncations and 10,000 seeded mutations are `Ok` or `Err`, never a runtime error; `tests.burn.test_simple_images` checks the encoder against the corpus's files byte for byte and has Pillow read what it writes. Once, on 2026-11-25, the eight reference test images of qoiformat.org (`qoi_test_images.zip`, 5.6 MB, not vendored: past the corpus's size limit) decoded to their PNGs' pixels as Pillow reads them, and seven of them encoded again byte for byte. The eighth, `edgecase.qoi`, takes the colour of an opening run (opaque black) from the table later on, which a decoder must allow (it stores every pixel's colour, a run's too) but `qoi.h`'s encoder never writes, as its table only gets colours it wrote out.
