# std.imageio

Images read and written in every format the standard library knows ([[MYLA-940]], the plan [[Project/Standard-library-roadmap/Images-vision-and-fonts#std.imageio (MYLA-940)]]): PNG, JPEG, GIF, TIFF, BMP, the Netpbm formats (PBM, PGM, PPM, PAM) and QOI, through [[Language/Standard-library/Png]], [[Language/Standard-library/Jpeg]], [[Language/Standard-library/Gif]], [[Language/Standard-library/Tiff]], [[Language/Standard-library/Bmp]], [[Language/Standard-library/Pnm]] and [[Language/Standard-library/Qoi]]. It is the module most programs import: `load` a file whatever its format, `save` one in the format its name asks for. A file is read by its contents, never by its name; it is written by its name. Images and errors are [[Language/Standard-library/Image]]'s (`Image8`, `Image16`, `ImageInfo`, `ImageError`).

```myla
import std.image as image
from std.image import Image8, Layout
import std.imageio as imageio
from std.imageio import Format

fun main() {
    // a 16x8 picture with a half-transparent row
    var img: Image8 = image.new(16, 8, Layout.Rgba, 0u8)
    for y in 0..8 {
        for x in 0..16 {
            let a = if y == 7 { 128u8 } else { 255u8 }
            img.set_color(x, y, image.rgba((x * 16) as uint8, (y * 32) as uint8, 200u8, a))
        }
    }
    // in memory, in every lossless format: decode finds the format itself
    for f in imageio.formats() {
        if f.lossless() {
            let file = imageio.encode(img, f)
            let back = imageio.decode(file).unwrap_or(img)
            print(f"{f.name()}: {file.len()} bytes, read back the same: {back.convert(Layout.Rgba) == img}")
        }
    }
    print(imageio.format_of("holiday/IMG_0042.JPG") == Some(Format.Jpeg))
    if let Ok(i) = imageio.info(imageio.encode(img, Format.Png)) {
        print(f"{i.format}: {i.width}x{i.height} {i.layout}, {i.bit_depth} bits")
    }
    match imageio.decode([60u8, 104u8, 116u8, 109u8, 108u8, 62u8]) {
        Ok(_) => print("decoded")
        Err(e) => print(f"{e}")
    }
    match imageio.save("picture.webp", img) {
        Ok(()) => print("saved")
        Err(e) => print(f"{e}")
    }
}
// output:
// png: 90 bytes, read back the same: true
// tiff: 316 bytes, read back the same: true
// bmp: 634 bytes, read back the same: true
// pnm: 578 bytes, read back the same: true
// qoi: 535 bytes, read back the same: true
// true
// png: 16x8 rgba, 8 bits
// not an image of this format
// unsupported: extension .webp
```

A program that needs one format only imports its codec, and checks and builds faster for it (see [Cost](#cost)).

[TOC]

## Functions

| Function | Result |
| --- | --- |
| `sniff(b: [uint8]) -> Option<Format>` | The format of the file `b` by its first bytes, None if it is none of them ([Formats](#formats)) |
| `format_of(path: str) -> Option<Format>` | The format a file name's extension names, in any case; None for another extension or none |
| `info(b: [uint8]) -> Result<ImageInfo, ImageError>` | What the file says of its image, as its codec's `info` gives it, without decoding: the size, the layout `decode` gives, the bits of a sample as stored, the frames (a GIF's) or pages (a TIFF's), `format` the format's `name()` |
| `decode(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>` | The image of the file `b`, its format found by `sniff`, the pixels as stored ([Reading](#reading)) |
| `decode16(b: [uint8], max_pixels: int64 = image.MAX_PIXELS) -> Result<Image16, ImageError>` | The same at 16 bits a sample: PNG, TIFF and PNM as their `decode16` give them, the other formats (8 bits at most) widened, each sample times 257 |
| `load(path: str, max_pixels: int64 = image.MAX_PIXELS) -> Result<Image8, ImageError>` | The image in the file at `path`, read by `decode`, and shown upright: a JPEG turned as its EXIF orientation says |
| `load16(path: str, max_pixels: int64 = image.MAX_PIXELS) -> Result<Image16, ImageError>` | `load` at 16 bits (`decode16`) |
| `encode(img: Image8, f: Format, quality: int = 90) -> [uint8]` | `img` as a file of `f`, as its codec's `encode` writes it by default ([Writing](#writing)); `quality` (1 to 100) is JPEG's |
| `encode16(img: Image16, f: Format, quality: int = 90) -> [uint8]` | `img` at 16 bits as PNG, TIFF and PNM (`encode16`), rounded to 8 (`img.to_u8()`) for the others |
| `save(path: str, img: Image8, quality: int = 90) -> Result<(), ImageError>` | `img` written to the file at `path` (created or replaced) in the format its extension names, as `encode` writes it |
| `save16(path: str, img: Image16, quality: int = 90) -> Result<(), ImageError>` | `save` at 16 bits (`encode16`) |
| `formats() -> [Format]` | Every format, in the enum's order |

```myla fragment
#derive(Eq, Hash)
pub enum Format { Png, Jpeg, Gif, Tiff, Bmp, Pnm, Qoi }
```

`f.name()` is the format's name as `ImageInfo.format` gives it (`"png"`, `"jpeg"`, `"gif"`, `"tiff"`, `"bmp"`, `"pnm"`, `"qoi"`), `f.extension()` the usual extension of its files, without the dot (`jpg`, `tif`, the name for the rest), and `f.lossless()` whether `encode` keeps every pixel of any 8-bit image: true but for JPEG and GIF. `Format` is `Eq` and `Hash` (a map key), but has no `impl Format`, so print `f.name()`: a module that declares a type named like a prelude trait can't name that trait in an `impl` (the module's `Format` hides the prelude's when another module imports it), a toolchain bug noted on [[MYLA-940]].

## Formats

| Format | `sniff` knows it by | `format_of` knows it by |
| --- | --- | --- |
| `Png` | the 8-byte signature `89 50 4E 47 0D 0A 1A 0A` | `.png` |
| `Jpeg` | `FF D8 FF` (the start of image and a marker) | `.jpg`, `.jpeg`, `.jpe`, `.jfif` |
| `Gif` | `GIF87a` or `GIF89a` | `.gif` |
| `Tiff` | `II*\0` (little endian) or `MM\0*` (big endian); BigTIFF's `II+\0` and `MM\0+` too, which std.tiff names as unsupported | `.tif`, `.tiff` |
| `Bmp` | `BM` | `.bmp`, `.dib` |
| `Pnm` | `P1` to `P7` and a whitespace byte | `.pbm`, `.pgm`, `.ppm`, `.pnm`, `.pam` |
| `Qoi` | `qoif` | `.qoi` |

An extension is what follows the last `.` of the file name (the part after the last `/` or `\`), unless the name starts with that dot (`.png` is a hidden file with no extension). Anything else is no format: `sniff` gives None and `decode`, `info` and `load` `BadSignature`, before any codec runs, and `save` gives `Unsupported("extension .webp")`, or `Unsupported("a file name without an extension")`. A file too short for its signature, such as a JPEG cut after `FF D8`, is `BadSignature` too, where its codec would say `Truncated`.

## Reading

`decode` gives what the codec's `decode` gives, the same pixels and the same errors: every file of the image corpus does, broken ones included (`tests/burn/test_imageio.py`). That is:

- **PNG** in its own layout (gray, gray and alpha, RGB, RGBA; a palette as RGB or RGBA), 16 bits rounded to 8;
- **JPEG** gray or RGB, the pixels as stored, not turned by the EXIF orientation;
- **GIF** the first frame as it is shown, `Rgba` (`gif.decode_all` and `gif.composite` give an animation's frames);
- **TIFF** the first page (`tiff.decode(b, page)` reads the others, `tiff.decode_f32` float samples, which `decode` rounds to 8 bits);
- **BMP** RGB, or RGBA with an alpha mask;
- **PNM** gray, gray and alpha, RGB or RGBA, any MAXVAL scaled to 8 bits;
- **QOI** RGB or RGBA.

`max_pixels` bounds what a file may ask for (all of a GIF's frames together), `TooLarge` past it before anything is allocated. Inputs are untrusted: a fuzz run of truncated and mutated files of every format gives `Ok` or `Err`, never a runtime error, also when a mutated header hands the file to another codec.

`load` reads the file (`std.fs`'s `read_bytes`; a file that can't be read is `ImageError.Io`, whose message is the `IoError`'s name, `NotFound`), decodes it, and turns a JPEG upright, `jpeg.apply_orientation(img, jpeg.orientation(b))`, as viewers do and as Pillow's `ImageOps.exif_transpose`: orientation 6 is a quarter turn clockwise, so a 48×32 photograph taken upright on its side loads 32×48. The extension plays no part: a PNG named `photo.jpg` loads as the PNG it is, and a JPEG named `.png` is turned all the same. `info` and `decode` describe the file as stored.

## Writing

`encode` writes each format as its codec's `encode` does with its defaults:

| Format | What it writes |
| --- | --- |
| PNG | zlib level 6, filters chosen a row at a time, the smallest colour type that loses nothing: gray if every pixel is gray, no alpha if every pixel is opaque |
| JPEG | baseline at `quality`, once std.jpeg can encode ([[MYLA-937]]); until then `encode` is a failure and `save` `Unsupported("jpeg encoding")`, writing nothing |
| GIF | one frame; at most 256 colours exactly, more reduced by `image.quantize` with dithering; alpha below 128 transparent, the rest opaque |
| TIFF | LZW with the horizontal predictor, strips of about 8 KB, the image's layout |
| BMP | 24 bits without alpha (gray as RGB), 32 bits with an alpha mask |
| PNM | the image's own kind: PGM for gray, PPM for RGB, PAM with alpha; MAXVAL 255 |
| QOI | RGB (gray as RGB) or RGBA |

So a lossless format gives back the same pixels, but not always in the same layout: compare `back.convert(Layout.Rgba)` with the original, as the example above does. `save` takes the format from the extension (`format_of`), so `save("out.png", img)` writes PNG, and for the Netpbm extensions the kind they name: `.pgm` gray and `.ppm` RGB (alpha dropped), `.pbm` black and white (a pixel's gray below half is black), `.pam` the layout as it is, `.pnm` the image's own kind (`pnm.encode_as`). `quality` matters only for JPEG; for the other formats' options (a PNG's compression level, a TIFF's compression, a GIF without dithering, plain PNM) call the codec. A file that can't be written (no such directory, no permission) is `ImageError.Io`.

`encode16` and `save16` write PNG, TIFF and PNM with 16 bits a sample and round to 8 for the others, which hold no more.

## Cost

std.imageio imports all seven codecs, so it costs a program more to check and to build than one codec does. A program that loads an image and prints its size through `imageio.load`, against the same through `png.decode` alone, one that imports the seven codecs itself (and calls each one's `info`), and `print("hi")`, on a shared 4-core x86-64 machine (2026-11-25, the best of seven runs of `build/myla` with the library it embeds):

| Program | `myla check` | `myla build` | Binary |
| --- | --- | --- | --- |
| `print("hi")` | 5 ms | 82 ms | 24 KB |
| `import std.png` | 35 ms | 180 ms | 108 KB |
| the seven codecs | 58 ms | | |
| `import std.imageio` | 81 ms | 426 ms | 352 KB |

With the library read from its files (`--stdlib lib`) the times are the same within a few milliseconds (8, 33 and 83 ms to check, 84, 181 and 405 ms to build). So `check` costs about 45 ms more than with std.png alone, most of it the other six codecs, and the binary holds every decoder and encoder: a program that reads one known format and cares about either should import that codec.

## Tests

The module's `#test` cases (on `sniff`, `format_of`, `info`, `decode`, `decode16`, `encode`, `encode16`, the extension rules) and test functions (every lossless format and layout in memory and through a temporary directory, 16 bits, GIF's colours, a file named for another format, the Netpbm kinds by extension, a JPEG turned by `load`, the errors, JPEG saved once std.jpeg encodes) pass interpreted and natively. `tests/burn/test_imageio.py` runs the image corpus (`tests/burn/data/images/`, MYLA-945) through `decode` against the manifest's pixels natively, `--checked` and the smallest file of each format interpreted, and fuzzes it plain and `--checked`; checks that `decode` and `info` are each codec's on every file, that `sniff` names every readable file's format, that a file under a wrong extension or none loads by its contents, that `load` turns the corpus's EXIF-oriented JPEGs to Pillow's `exif_transpose` pixels (vendored hashes), that every readable file saved and loaded in each format comes back with the same pixels (16-bit files through `save16` and `load16` too), and, with Pillow installed, that Pillow reads what `save` wrote as the same pixels.
