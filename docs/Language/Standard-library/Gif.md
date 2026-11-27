# std.gif

GIF images and animations ([[MYLA-964]], D313): GIF87a and GIF89a, global and local palettes, transparency, interlacing, each frame's delay and disposal (the graphic control extension) and the NETSCAPE2.0 loop count, read and written. The pixel data is LZW, from [[Language/Standard-library/Compress#LZW and PackBits]]; the images are [[Language/Standard-library/Image]]'s `Image8`, and the encoder reduces colours with its `quantize`. The plan is [[Project/Standard-library-roadmap/Images-vision-and-fonts#std.gif (MYLA-964)]].

```myla
import std.gif as gif
from std.gif import Animation, Frame, Disposal
import std.image as image
from std.image import Layout
import std.encoding as encoding

fun main() {
    // a 2x2 GIF Pillow wrote: red, green, blue, white
    let b = encoding.hex_decode("47494638376102000200810000ff000000ff000000ffffffff2c000000000200020000080700010410302020003b").unwrap_or([])
    match gif.decode(b) {
        Ok(img) => print(f"{img.width}x{img.height} {img.layout}, {img.color_at(1, 0)} {img.color_at(0, 1)}")
        Err(e) => print(f"error: {e}")
    }

    // an animation: a dot moving over gray, the third frame with a hole
    var frames: [Frame] = []
    for t in 0..3 {
        var img = image.new(8, 4, Layout.Rgba, 255u8)
        img.fill([90u8, 90u8, 90u8, 255u8])
        img.set_color(2 * t, 1, image.rgb(255u8, 200u8, 0u8))
        if t == 2 {
            img.set_color(7, 3, image.rgba(0u8, 0u8, 0u8, 0u8))
        }
        frames.push(Frame { image: img, x: 0, y: 0, delay_ms: 80, disposal: Disposal.Background })
    }
    let a = Animation { width: 8, height: 4, loops: 0, background: image.rgba(0u8, 0u8, 0u8, 0u8), frames: frames }
    let file = gif.encode_all(a)
    match gif.decode_all(file) {
        Ok(back) => {
            for f in back.frames {
                print(f"{f.image.width}x{f.image.height} at ({f.x}, {f.y}), {f.delay_ms} ms, then {f.disposal}")
            }
            let shown = gif.composite(back)
            print(f"loops {back.loops}, shown as made: {shown == gif.composite(a)}, the hole: {shown[2].color_at(7, 3).a}")
        }
        Err(e) => print(f"error: {e}")
    }
}
// output:
// 2x2 rgba, #00ff00ff #0000ffff
// 8x4 at (0, 0), 80 ms, then Keep
// 8x3 at (0, 1), 80 ms, then Background
// 8x3 at (0, 1), 80 ms, then Keep
// loops 0, shown as made: true, the hole: 0
```

Every pixel is `Rgba`, whatever the file's palettes: the transparent index of a frame's palette has alpha 0 (and keeps its colour, as Pillow shows it), the others 255. Decoders take a `[uint8]` and encoders return one, as std.compress's functions do; inputs are untrusted (every offset is checked; a fuzz run of the corpus's files cut short and mutated gives `Ok` or `Err`, never a runtime error).

[TOC]

## Types

```myla fragment
pub enum Disposal { Unspecified, Keep, Background, Previous }
pub struct Frame { image: Image8, x: int, y: int, delay_ms: int, disposal: Disposal }
pub struct Animation { width: int, height: int, loops: int, background: Color, frames: [Frame] }
```

- A `Frame` is what the file holds: its own rectangle, drawn with its top left corner at `(x, y)` of the canvas, shown for `delay_ms` milliseconds (GIF stores hundredths of a second, so a decoded delay is a multiple of 10), then disposed of. Its image may be any layout in an animation a program makes; decoded, it is `Rgba`.
- `Disposal` is the graphic control extension's method, `d.code()` its number and `disposal_of(n)` the other way (the reserved 4 to 7 are `Unspecified`): `Unspecified` (0) and `Keep` (1) leave the frame; `Background` (2) clears its rectangle to the animation's background; `Previous` (3) puts back what was there before it.
- An `Animation` is a `width` by `height` canvas and its frames. `loops` is the NETSCAPE2.0 loop count: 0 loops forever, -1 means the file has no loop extension (it is shown once). `background` is the canvas before the first frame and what `Background` clears to. The decoder sets it as Pillow does: the first frame's transparent colour with alpha 0 if it has a transparent index, else the global palette's background colour, opaque. Browsers clear to transparent; a program that wants that sets `a.background = image.rgba(0u8, 0u8, 0u8, 0u8)`.

## Decoding

| Function | Result |
| --- | --- |
| `decode(b, max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>` | The first frame as it is shown: the whole canvas, `Rgba` (equal to `composite(decode_all(b)?)[0]`, without reading the other frames) |
| `decode_all(b, max_pixels: int64 = image.MAX_PIXELS) -> Result<Animation, ImageError>` | Every frame, each its own rectangle |
| `info(b) -> Result<ImageInfo, ImageError>` | The canvas, `Rgba`, `bit_depth` 8 and the number of frames, without decoding a pixel; `format` is `"gif"` |

- **The canvas** is the logical screen, grown to hold the first frame where that frame is bigger (as Pillow and browsers do); later frames are clipped to it.
- **Pixels:** an index past its palette is opaque black; a frame whose LZW data ends before its last pixel has the rest transparent (alpha 0); a file with neither a global nor a local palette reads its indices as gray levels (Pillow's choice). The minimum code size must be 1 to 8.
- **Errors:** a signature other than `GIF87a` or `GIF89a` is `BadSignature`; a file that ends inside its header, a palette, a block or the pixel data is `Truncated` (a missing trailer after a whole frame is fine, and so is any byte that starts no block once a frame was read: decoding ends there, as in Pillow); LZW data with a code past its table, a bad minimum code size, or more pixels than its rectangle holds is `Corrupt`.
- **`max_pixels`** counts, for each frame, its own rectangle and the canvas `composite` makes for it, all frames together: a million 1x1 frames on a large canvas is a bomb too. Past it, `TooLarge` with the count so far, before the frame is decoded; the canvas alone is checked first.

## Compositing

`composite(a: Animation) -> [Image8]` gives each frame as it is shown, `a.width` by `a.height`, `Rgba`. The canvas starts as `a.background`; a frame's pixels with alpha 0 leave the canvas as it is and the others replace it (GIF's transparency is all or nothing), clipped to the canvas; then its disposal applies to its rectangle before the next frame. Over the corpus (`tests/burn/data/images/gif/`, each disposal method, local palettes, transparency, interlacing) it gives exactly Pillow's frames converted to RGBA.

## Encoding

| Function | Result |
| --- | --- |
| `encode(img: Image8, dither: bool = true) -> [uint8]` | One frame, any layout |
| `encode_all(a: Animation, dither: bool = true) -> [uint8]` | Every frame as `composite(a)` shows it, with its delay and `a.loops` |

- **Colours:** a pixel with alpha below 128 is transparent, the others opaque. A frame of at most 256 colours keeps them exactly (255 when it needs the transparent entry); one with more goes through `image.quantize` (median cut), with Floyd–Steinberg dithering if `dither`. Each frame gets its palette: the first frame's is the global one, the others are local where they differ.
- **Frames:** `encode_all` writes the first frame whole and each later one as the rectangle of what changed since the one before, with `Keep`; where pixels become transparent, the frame before is disposed of with `Background` over a rectangle that holds them. So a decoder's frames differ from `a.frames`, but `composite` of what it reads is `composite(a)` with alpha made all or nothing (exactly, for frames of at most 256 colours). Delays are rounded to hundredths of a second; `a.loops` below 0 writes no loop extension. Pillow reads the output to the same frames, delays and loop count (`tests/burn/test_gif.py`).
- **Header:** `GIF87a` for one frame without transparency or a delay, else `GIF89a`. More than 65535 pixels wide or high, or an animation without frames, is a failure.

## Speed

Natively on x86-64, on a machine shared with other work (2026-11-25), against Pillow 13 on the same machine:

| Work | std.gif | Pillow |
| --- | --- | --- |
| decode a 1024x1024 frame of 256 colours | 25 ms | 4 ms |
| encode a 1024x1024 photograph-like image (quantised to 256, dithered) | 550 ms | 600 ms (its quantize alone 540 ms) |
| encode a 1024x1024 image of 4 colours | 130 ms | |
| `encode_all` of 100 frames of 256x256, every pixel changing (quantised) | 4.2 s | |
| `encode_all` of 100 frames of 256x256, a moving square (4 colours) | 0.15 s, 13 KB | |
| `decode_all` and `composite` of those 100 frames | 0.13 s and 0.04 s; 3 ms and 7 ms | |

Most of a decode is allocating its buffers: std.list's `filled` pushes one sample at a time ([[MYLA-949]]); the encoder's time is `image.quantize`'s.
