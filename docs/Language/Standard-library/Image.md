# std.image

The image type the codecs, std.imgproc, std.draw and std.font share ([[MYLA-933]], D311, the plan [[Project/Standard-library-roadmap/Images-vision-and-fonts]]): `Image<S>` of `uint8`, `uint16` or `float32` samples in one of four layouts, colours and rectangles, the one error type of every codec, layout and sample conversions, the exact geometry, quantizing to a palette, and a preview in the terminal. It reads and writes no file format: the codecs do.

```myla
import std.image as image
from std.image import Image8, Layout

fun main() {
    // a 4x2 ramp from red to blue, a pixel at a time
    var img: Image8 = image.new(4, 2, Layout.Rgb, 0u8)
    let red = image.rgb(255u8, 0u8, 0u8)
    let blue = image.parse_color("#0000ff").unwrap_or(red)
    for y in 0..img.height {
        for x in 0..img.width {
            img.set_color(x, y, red.lerp(blue, (x as float32) / 3.0f32))
        }
    }
    print(f"{img.width}x{img.height} {img.layout}, {img.data.len()} samples")
    print(f"pixel (1, 0) is {img.color_at(1, 0)}, its green {img[(1, 0, 1)]}")

    // gray by Pillow's BT.601 formula, then turned clockwise
    let gray = img.convert(Layout.Gray).rotate90()
    var row = ""
    for v in gray.row(0) {
        row = row + f" {v}"
    }
    print(f"gray turned: {gray.width}x{gray.height}, first row{row}")

    // two colours, and the pixels mapped to them
    let q = image.quantize(img, 2, false)
    print(f"palette {q.palette[0]} {q.palette[1]}, first index {q.indices[0]}")

    // a crop that reaches past the image is clipped
    let c = img.crop(image.rect(2, 1, 10, 10))
    print(f"crop {c.width}x{c.height}, gray to float {gray.to_f32()[(0, 0, 0)]}")
}
// output:
// 4x2 rgb, 24 samples
// pixel (1, 0) is #aa0055ff, its green 0
// gray turned: 2x4, first row 76 76
// palette #2b00d5ff #d5002bff, first index 1
// crop 2x1, gray to float 0.29803923
```

## Types

```myla fragment
pub struct Image<S> { width: int, height: int, layout: Layout, data: [S] }
pub typealias Image8 = Image<uint8>
pub typealias Image16 = Image<uint16>
pub typealias ImageF = Image<float32>

pub enum Layout { Gray, GrayAlpha, Rgb, Rgba }     // channels(), has_alpha(), is_color(); Format: "gray", "gray+alpha", "rgb", "rgba"
pub struct Color { r: uint8, g: uint8, b: uint8, a: uint8 }   // sRGB, straight alpha; Eq, Hash
pub struct Rect { x: int, y: int, w: int, h: int }             // Eq, Hash
pub struct ImageInfo { width: int, height: int, layout: Layout, bit_depth: int, frames: int, format: str }
pub struct Indexed { width: int, height: int, palette: [Color], indices: [uint8] }
pub const MAX_PIXELS: int64 = 0x10000000    // what a decoder allocates unless told otherwise
pub const MAX_SAMPLES: int64 = 2147483647   // a list's limit
```

The samples are interleaved row by row without padding: sample `c` of the pixel `(x, y)` is `data[(y * width + x) * channels + c]` (`img.offset(x, y, c)`). Integer samples are full scale at their maximum (255, 65535), floats at 1.0. `Image` is `Eq`.

`Sample` is the trait of the three sample types. Its functions are called on the type (`uint8.luma(r, g, b)`, `S.max_value()` in generic code):

| Function | Result |
| --- | --- |
| `max_value() -> Self` | 255, 65535 or 1.0 |
| `s.to_f32() -> float32` | The value, unscaled: `255u8` is 255.0 |
| `from_f32(v: float32) -> Self` | Back, rounded and clamped for the integers (NaN is 0) |
| `s.to_unorm8() -> uint8` | Scaled to 0..255: 16 bits as libpng rounds them, `(v * 255 + 32767) / 65535`; floats times 255, rounded and clamped |
| `from_unorm8(v: uint8) -> Self` | From 0..255: 16 bits times 257, floats divided by 255 |
| `luma(r, g, b) -> Self` | BT.601 luma. Integers in fixed point, `(R * 19595 + G * 38470 + B * 7471 + 0x8000) >> 16`: for 8 bits exactly Pillow's `convert("L")`, all 2^24 triples checked; floats `0.299 R + 0.587 G + 0.114 B` |
| `s.mul_alpha(a) -> Self`, `s.div_alpha(a) -> Self` | Premultiplying and back: `v * a / max` rounded, `v * max / a` truncated and clamped (`v` where `a` is 0), in integers for the integer types |

## Making and reading images

| Function or method | Result |
| --- | --- |
| `new<S: Sample>(width, height, layout, fill: S) -> Image<S>` | Every sample `fill`. A negative size or more than 2^31 − 1 samples is a failure, as for `grid.new` (D184) |
| `from_data<S: Sample>(width, height, layout, data: [S]) -> Result<Image<S>, ImageError>` | The image around `data`; `Mismatch` unless it holds `width * height * channels` samples |
| `img[(x, y, c)]`, `img[(x, y, c)] = v` | A sample. Out of bounds is a failure, as for a list |
| `img.get(x, y, c) -> Option<S>`, `img.in_bounds(x, y)`, `img.channels()`, `img.offset(x, y, c)`, `img.bounds() -> Rect` | The checked read, the bounds, the index in `data` |
| `img.color_at(x, y) -> Color` | The pixel in 8 bits: gray repeated, opaque without alpha |
| `img.set_color(var self, x, y, c: Color)` | Sets the pixel: its luma in a gray layout, its alpha dropped without one |
| `img.row(y) -> [S]` | The samples of a row |
| `img.channel(c) -> Image<S>` | One channel as a gray image |
| `merge<S: Sample>(planes: [Image<S>], layout) -> Result<Image<S>, ImageError>` | Gray planes interleaved into `layout`; `Mismatch` for the wrong number of planes, or one that isn't gray or the first one's size |
| `sample_count(width, height, channels) -> Option<int64>`, `check_size(width, height, channels, max_pixels) -> Result<(), ImageError>` | For decoders: a size in `int64`, and `TooLarge` before allocating past the limits |

## Layouts and sample types

| Method | Result |
| --- | --- |
| `img.convert(layout) -> Image<S>` | Colour to gray is `S.luma`; gray to colour repeats it; gaining alpha makes it opaque, losing it drops it (as Pillow's `convert`) |
| `img.to_f32() -> ImageF` | Scaled to 0..1 |
| `img.to_u8() -> Image8` | `to_unorm8` of every sample |
| `img.to_u16() -> Image16` | 8 bits times 257, floats times 65535, rounded and clamped |
| `img.map<T: Sample>(f: (S) -> T) -> Image<T>` | `f` of every sample, alpha included |

## Geometry and alpha

Each returns a new image, except `paste` and `fill`, which change it.

| Method | Result |
| --- | --- |
| `img.crop(r: Rect) -> Image<S>` | The part inside `r`: smaller where `r` reaches past the image, 0 by 0 where it misses it |
| `img.paste(var self, src: Image<S>, x, y)` | `src` copied with its corner at `(x, y)`, converted to this layout, clipped to the image. The samples replace these, alpha too: std.draw blends |
| `img.fill(var self, v: [S])` | Every pixel `v`, a sample a channel (another length is a failure) |
| `img.flip_h()`, `img.flip_v()` | Mirrored left to right, top to bottom |
| `img.rotate90()`, `img.rotate180()`, `img.rotate270()` | Turned clockwise by a quarter, a half and three quarters: `rotate90` is Pillow's `Transpose.ROTATE_270` |
| `img.transpose()` | Mirrored along the main diagonal: `(x, y)` goes to `(y, x)` |
| `img.premultiplied()`, `img.unpremultiplied()` | The colour samples times alpha, rounded, and divided by it again, truncated and clamped (left alone where alpha is 0): for 8 bits exactly Pillow's conversions to `"RGBa"` and back, all 65,536 pairs checked. Unchanged without alpha |

## Colours and rectangles

| Function or method | Result |
| --- | --- |
| `rgb(r, g, b)`, `rgba(r, g, b, a)` | A colour, `rgb` opaque |
| `parse_color(s) -> Option<Color>` | `#rgb`, `#rgba`, `#rrggbb` or `#rrggbbaa`, digits in either case |
| `c.with_alpha(a)` | The colour with alpha `a` |
| `c.lerp(d: Color, t: float32) -> Color` | A fraction `t` (clamped to 0..1) of the way to `d`, alpha too, rounded |
| `f"{c}"` | `#rrggbbaa` in lower case, which `parse_color` reads back |
| `rect(x, y, w, h)` | A rectangle |
| `r.contains(x, y)`, `r.is_empty()`, `r.intersect(o) -> Rect` | A pixel inside; no pixel at all; the pixels inside both, `rect(0, 0, 0, 0)` if none (computed in `int64`, so a rectangle near the `int` limit doesn't overflow) |

## Palettes

`quantize(img: Image8, colors: int, dither: bool = true) -> Indexed` reduces an image of any layout to at most `colors` colours (1 to 256, else a failure), as PNG palettes and GIF need:

- If it has that few colours, the palette is exactly them, in order of their `r, g, b, a`, and nothing changes.
- Else the palette comes by median cut (Heckbert's): the box of colours with the widest channel range, alpha counted like the others, is split at its median pixel until there are `colors` boxes, and each colour is its box's mean. Each pixel then gets the nearest colour (squared distance in `r, g, b, a`, the lowest index among equals), with Floyd–Steinberg dithering of red, green and blue if `dither`.
- It is all integers, so the palette and the indices are the same on every target.

`ix.to_image() -> Image8` gives the pixels back: `Rgb` if every palette colour is opaque, else `Rgba`; an index past the palette is transparent black.

## The terminal preview

`ansi<S: Sample>(img: Image<S>, columns: int) -> str` draws the image in a truecolor terminal with half blocks, two pixels a character cell (`▀`, its top the foreground colour and its bottom the background), each line ending in a reset and a newline, for looking at an intermediate result without a viewer:

```myla fragment
print(image.ansi(img, 80))
```

The image is scaled down to `columns` wide (never up) with the height in proportion; each pixel of the preview is the mean of the pixels it covers (an area filter), weighted by alpha. A pixel less than half opaque shows the terminal's own background.

## Errors

`ImageError` is the error of every codec, std.imageio and std.imgproc (D168): `Truncated`, `BadSignature`, `Unsupported(str)`, `Corrupt(str)`, `Checksum`, `TooLarge(int64)` (the pixels asked for), `Mismatch(str)` and `Io(IoError)`, with `e.message()` and `f"{e}"`.

## Speed

The operations work on `data` with index arithmetic, a loop for each case and no allocation for a pixel, so natively they run about as fast as the loop a program writes by hand. Natively (`myla build`, bounds checks on, a shared x86-64 machine whose runs vary by 10 to 15 %, 2026-11-24, `6f95a1a`), the fastest of five to ten runs, over several runs, on a 4096×4096 RGBA image:

| Work | std.image | The loop by hand |
| --- | --- | --- |
| `convert(Layout.Gray)` | 76 to 90 ms | 74 to 86 ms |
| `flip_h()` | 200 to 228 ms | 197 to 226 ms |
| `premultiplied()` | 222 to 232 ms | 226 to 228 ms |
| `to_f32()` | 1.44 to 1.50 s | 1.36 s |

Lists of `float32` are the slow part natively: making one this size alone took 0.48 s. `quantize` of a 1024×1024 image of about a million colours to 256 took 0.53 to 0.59 s with dithering and 0.69 to 0.70 s without (the nearest colour of each distinct colour), most of it the nearest-colour search; an image of 256 colours or fewer takes a sort, 0.09 s. The interpreter is much slower ([[Project/Standard-library-roadmap/Images-vision-and-fonts#What was measured]]), so `#test` cases use images of a few pixels.
