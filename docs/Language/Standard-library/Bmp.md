# std.bmp

Windows bitmaps ([[MYLA-960]], the plan [[Project/Standard-library-roadmap/Images-vision-and-fonts]]): the format of Windows' clipboard and of the images inside icons. It reads what is in use, from 1-bit palettes to 32 bits with an alpha mask, uncompressed or run-length encoded, and writes 24 bits, or 32 when the image has alpha. Images are [[Language/Standard-library/Image]]'s.

```myla
import std.image as image
from std.image import Image8, Layout
import std.bmp as bmp

fun main() {
    // a 3x2 image with alpha: written at 32 bits, read back the same
    var img: Image8 = image.new(3, 2, Layout.Rgba, 255u8)
    img.set_color(1, 0, image.rgba(10u8, 20u8, 30u8, 128u8))
    let file = bmp.encode(img)
    print(f"{file.len()} bytes")
    print(bmp.decode(file, image.MAX_PIXELS).unwrap_or(img) == img)
    if let Ok(i) = bmp.info(file) {
        print(f"{i.width}x{i.height} {i.layout}")
    }

    // without alpha it is 24 bits, each row padded to four bytes
    let opaque = img.convert(Layout.Rgb)
    print(f"{bmp.encode(opaque).len()} bytes")

    // a file cut short, and one that asks for too much
    match bmp.decode(file[:60], image.MAX_PIXELS) {
        Ok(_) => print("decoded")
        Err(e) => print(f"{e}")
    }
    match bmp.decode(file, 5i64) {
        Ok(_) => print("decoded")
        Err(e) => print(f"{e}")
    }
}
// output:
// 146 bytes
// true
// 3x2 rgba
// 78 bytes
// truncated input
// image too large: 6 pixels
```

## Functions

| Function | Result |
| --- | --- |
| `info(b: [uint8]) -> Result<ImageInfo, ImageError>` | What the headers say: size, layout (`Rgb` or `Rgba`), `bit_depth` (a palette's index bits for 1 to 8 bits a pixel, the widest mask's bits for 16 and 32, 8 for 24), one frame, `format` `"bmp"` |
| `decode(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>` | The image at 8 bits a sample, `Rgb` or `Rgba` |
| `encode(img: Image8) -> [uint8]` | The image as a BMP file, bottom-up: 24 bits (`BI_RGB`, a `BITMAPINFOHEADER`) without alpha, gray repeated; 32 bits (`BI_BITFIELDS` with an alpha mask, a `BITMAPV4HEADER`, sRGB) with it |

## Reading

`decode` reads the core header of OS/2 1.x (12 bytes) and `BITMAPINFOHEADER` (40) to `BITMAPV5HEADER` (124), with the V2 and V3 headers' masks; a negative height is a top-down image. What it reads:

| Bits a pixel | Compression | Gives |
| --- | --- | --- |
| 1, 4, 8 | `BI_RGB`, and `BI_RLE4` (4 bits) or `BI_RLE8` (8 bits) | `Rgb` through the palette |
| 16 | `BI_RGB` (5-5-5), `BI_BITFIELDS`, `BI_ALPHABITFIELDS` | `Rgb`, or `Rgba` with an alpha mask |
| 24 | `BI_RGB` | `Rgb` |
| 32 | `BI_RGB` (the fourth byte unused), `BI_BITFIELDS`, `BI_ALPHABITFIELDS` | `Rgb`, or `Rgba` with an alpha mask |

A palette has the header's number of colours, or 2^bits if it says 0; an index past it is black, as in Pillow. A channel of a mask with fewer than 8 bits is scaled as Pillow scales it, truncated, `v * 255 / (2^bits - 1)`; a mask of more bits is scaled down the same way. The masks of `BI_BITFIELDS` follow a 40-byte header, or are its own in a V2 header and later; `BI_RGB` ignores the masks of a V4 or V5 header, as Pillow does, so its 32 bits are opaque RGB.

In RLE8 and RLE4 a pair of bytes is a run of an index (in RLE4 two indices alternating), the end of a line, a jump right and up, the end of the bitmap, or a stretch of indices as they are, padded to two bytes. The pixels a jump or an early end of line passes over are index 0, and a run past the end of its row is cut there, as Pillow reads them. The data may stop after the last row's end of line, without the end of the bitmap; stopping earlier is `Truncated`.

A file shorter than its rows is `Truncated`, pixel data said to be past the end of the file `Corrupt`, another depth or compression (JPEG and PNG inside a BMP among them) `Unsupported`, a signature other than `BM` `BadSignature`. A header that asks for more than `max_pixels` pixels is `TooLarge` before anything is allocated.

## Speed

Natively (`myla build`, a shared 4-core x86-64 machine, 2026-11-25), the best of three runs on a 4096×4096 RGB image (50 MB, 24 bits): `encode` 120 to 124 ms, `decode` 113 to 114 ms, about 420 MB a second; most of the time is making the 50 MB list.

## Tests

The module's 22 cases pass interpreted, natively and on wasm32 under Node: `#test` cases on `info`, `decode`, `encode` and the helpers, and test functions with files built by hand for each depth, palette, both RLEs (runs, stretches, jumps, ends, overruns), 5-6-5 and 5-5-5, alpha masks, a core header, images of no pixels with a side of 2^31 - 1 (read and written at once, not row by row) and the errors, and every layout round-tripping through `encode`. The corpus (`tests/burn/data/images/bmp/`, written by Pillow and by `_images_vendor.py`) decodes to Pillow's pixels (`tests.burn.test_images`' `BmpDecoder`), natively, `--checked` and interpreted, and its truncations and 10,000 seeded mutations are `Ok` or `Err`, never a runtime error; Pillow reads every file `encode` writes from the corpus to the same pixels (`tests.burn.test_simple_images`).
