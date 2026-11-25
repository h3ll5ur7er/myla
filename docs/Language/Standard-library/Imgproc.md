# std.imgproc

Image processing over std.image's `Image<S>` ([[Project/Standard-library-roadmap/Images-vision-and-fonts#std.imgproc (MYLA-941, MYLA-944)]]). Tier A ([[MYLA-941]]): colour and point operations, resizing and warps, filters and derivatives, morphology, Canny's edges, corners, template matching, connected components, the distance transform and quality measures. Tier B ([[MYLA-944]]): contours and shapes, Hough transforms, FAST and ORB features and their matching, robust homographies and affine maps (RANSAC), optical flow, and the bilateral filter, fast rectangle morphology, the watershed and CLAHE. The module imports std.image, std.vector32, std.matrix32, std.unionfind, std.random, std.float, std.list, std.option and std.math.

```myla
import std.image as image
from std.image import Image8, Layout
import std.imgproc as imgproc

fun main() {
    // a 16 by 10 gray image: two bright squares on a dark ramp
    var img: Image8 = image.new(16, 10, Layout.Gray, 0u8)
    for y in 0..10 {
        for x in 0..16 {
            let a = x >= 2 && x < 6 && y >= 2 && y < 6
            let b = x >= 9 && x < 14 && y >= 4 && y < 8
            img[(x, y, 0)] = if a || b { 220u8 } else { (x * 3) as uint8 }
        }
    }
    let t = imgproc.otsu(img)
    let blobs = img |> imgproc.threshold(t) |> imgproc.components()
    print(f"otsu {t}, {blobs.count} blobs")
    for l in 1..blobs.count + 1 {
        let r = blobs.stats[l]
        print(f"  {r.area} px at ({r.bbox.x}, {r.bbox.y}), {r.bbox.w}x{r.bbox.h}, centre {r.centroid}")
    }
    let edges = img |> imgproc.gaussian_blur(0.7f32) |> imgproc.canny(60.0f32, 150.0f32)
    for y in 0..edges.height {
        var row = ""
        for x in 0..edges.width {
            row = row + (if edges[(x, y, 0)] > 0u8 { "#" } else { "." })
        }
        print(row)
    }
    let small = imgproc.resize(img, 8, 5, imgproc.Filter.Area)
    let first = small.data[0:8].map((v) => f"{v}").join(" ")
    print(f"{small.width}x{small.height}, its first row {first}")
}
// output:
// otsu 45, 2 blobs
//   16 px at (2, 2), 4x4, centre (3.5, 3.5)
//   20 px at (9, 4), 5x4, centre (11, 5.5)
// ................
// ................
// ..####..........
// ..#..#..........
// ..#..#...#####..
// ..####...#...#..
// .........#...#..
// .........#####..
// ................
// ................
// 8x5, its first row 2 8 14 20 26 32 38 44
```

## Conventions

- **Free functions, image first**, so they chain with `|>`: `img |> imgproc.gray() |> imgproc.gaussian_blur(1.4f32) |> imgproc.canny(40.0f32, 120.0f32)`.
- **Sample types.** Functions that make sense for any sample type are generic over `S: Sample` (`resize`, the warps, `pad`, the pyramids, `convolve`, the blurs, the derivatives, `invert`, `blend`, `abs_diff`, `match_template`, `integral`, `harris`, the quality measures); the rest take an `Image8`. Integer images come back as integer images, rounded (halves up) and clamped; a result that is signed or fractional (derivatives, Harris's response, template scores, distances) is an `ImageF` **in the input's sample units**: the Sobel derivative of an `Image8` is in units of 0 to 255, not 0 to 1. `normalize_f` maps such an image to 0..255 for display.
- **Channels.** Filters, warps and morphology work on every channel alike, alpha too. Point operations (`invert`, `lut`, `adjust`, `gamma`, `threshold`, `equalize`, `normalize`) leave alpha alone. `gray` and `to_rgb` drop alpha. `canny` and `otsu` work on the gray of a colour image; `harris`, `good_features`, `components` and `distance_transform` on the first channel.
- **Coordinates.** Pixel (x, y) is the point (x, y) for the warps (OpenCV's convention: `warp_affine` with a translation by (1, 0) moves every pixel one to the right). `resize` follows Pillow, whose pixels are squares with their centres at (x + 0.5, y + 0.5).
- **Borders.** `Border { Constant(float32), Replicate, Reflect, Reflect101, Wrap }` is OpenCV's set: with a row `abcdefgh`, `Constant(v)` is `vvv|abcdefgh|vvv` (`v` in sample units), `Replicate` `aaa|abcdefgh|hhh`, `Reflect` `cba|abcdefgh|hgf`, `Reflect101` `dcb|abcdefgh|gfe` (the default) and `Wrap` `fgh|abcdefgh|abc`. Morphology ignores the pixels past the edge.
- **Failures.** A size or layout that doesn't fit (`abs_diff` of two sizes, a template larger than the image, `ssim` of an image under 11 by 11) is `Err(ImageError.Mismatch(…))`. A bad argument that is a programming error (a kernel of the wrong length, a negative radius to `pad`, a singular matrix to a warp, an even block to `adaptive_threshold`) is a failure, as an index out of range is.

## Colour and point operations

| Function | What it gives |
| --- | --- |
| `gray(img: Image8) -> Image8` | Gray, with Pillow's integer luma for colour, `(R·19595 + G·38470 + B·7471 + 0x8000) >> 16` (ITU-R 601-2): exactly Pillow's `convert("L")` |
| `to_rgb(img: Image8) -> Image8` | RGB: gray repeated, alpha dropped |
| `to_hsv(img: Image8) -> ImageF` | Hue in degrees (0 to 360), saturation and value (0 to 1), as Python's `colorsys` |
| `from_hsv(f: ImageF) -> Image8` | RGB from hue, saturation and value |
| `to_linear(img: Image8) -> ImageF` | The sRGB transfer function undone: linear light, 0 to 1 |
| `to_srgb(f: ImageF) -> Image8` | Linear light back to sRGB |
| `invert<S>(img: Image<S>) -> Image<S>` | `max - v` |
| `lut(img: Image8, table: [uint8]) -> Image8` | `table[v]` (a value past the end of a short table stays) |
| `adjust(img: Image8, brightness: float32, contrast: float32 = 1.0f32) -> Image8` | `(v - 127.5)·contrast + 127.5 + brightness` |
| `gamma(img: Image8, g: float32) -> Image8` | `255·(v / 255)^g`: above 1 darkens |
| `threshold(img: Image8, t: uint8, mode: Threshold = Threshold.Binary, max: uint8 = 255u8) -> Image8` | OpenCV's five types: `Binary` (max if v > t, else 0), `BinaryInv`, `Trunc` (min(v, t)), `ToZero` (v if v > t, else 0), `ToZeroInv` |
| `otsu(img: Image8) -> uint8` | Otsu's threshold: the first `t` that maximises the variance between `v <= t` and `v > t` |
| `adaptive_threshold(img: Image8, block: int, c: float32, method: Adaptive = Adaptive.Mean) -> Image8` | 255 where the gray is above its `block` by `block` mean (or Gaussian-weighted mean, `Adaptive.Gaussian`, sigma as OpenCV's) minus `c`; the border replicates |
| `in_range(img: Image8, lo: Color, hi: Color) -> Image8` | A mask: 255 where every channel lies within `lo` to `hi` |
| `histogram(img: Image8, channel: int = 0) -> [int]` | 256 counts |
| `equalize(img: Image8) -> Image8` | Histogram equalisation, OpenCV's formula, each colour channel |
| `normalize(img: Image8, lo: uint8 = 0u8, hi: uint8 = 255u8) -> Image8` | Stretched linearly so the extremes are `lo` and `hi` |
| `normalize_f(f: ImageF) -> Image8` | A float image (a gradient, a response) to 0..255 for display |
| `abs_diff<S>(a: Image<S>, b: Image<S>) -> Result<Image<S>, ImageError>` | `|a - b|` |
| `blend<S>(a: Image<S>, b: Image<S>, alpha: float32) -> Result<Image<S>, ImageError>` | `a + (b - a)·alpha` |
| `apply_mask<S>(img: Image<S>, mask: Image8) -> Result<Image<S>, ImageError>` | 0 where the mask is 0 |

## Geometry

| Function | What it gives |
| --- | --- |
| `resize<S>(img: Image<S>, w: int, h: int, filter: Filter = Filter.Bilinear) -> Image<S>` | The image resized, `Filter { Nearest, Bilinear, Bicubic, Area, Lanczos3 }` |
| `thumbnail<S>(img: Image<S>, max_w: int, max_h: int, filter: Filter = Filter.Area) -> Image<S>` | Shrunk to fit, the aspect ratio kept; never enlarged |
| `rotate<S>(img: Image<S>, degrees: float32, fill: Color = …, expand: bool = false) -> Image<S>` | Turned counterclockwise about the centre, bilinear; `expand` makes it large enough for the whole turned image |
| `warp_affine<S>(img: Image<S>, m: Mat3, w: int, h: int, filter: Filter = Filter.Bilinear, border: Border = Border.Constant(0.0f32)) -> Image<S>` | The image under the affine map `m` (source to result, OpenCV's `warpAffine`) |
| `warp_perspective<S>(img: Image<S>, m: Mat3, w: int, h: int, filter: Filter = …, border: Border = …) -> Image<S>` | Under the homography `m` |
| `affine_from(src: [Vec2], dst: [Vec2]) -> Option<Mat3>` | The affine map of three points to three |
| `perspective_from(src: [Vec2], dst: [Vec2]) -> Option<Mat3>` | The homography of four points to four |
| `pad<S>(img: Image<S>, top: int, right: int, bottom: int, left: int, border: Border = Border.Constant(0.0f32)) -> Image<S>` | Pixels added through the border |
| `pyr_down<S>(img: Image<S>, border: Border = Border.Reflect101) -> Image<S>` | Blurred by the 5 by 5 binomial kernel and halved, (w + 1) / 2 by (h + 1) / 2 |
| `pyr_up<S>(img: Image<S>, border: Border = Border.Reflect101) -> Image<S>` | Doubled, zeros between the pixels blurred by the binomial kernel times 4 |

`resize` of an `Image8` is Pillow's `Image.resize` pixel for pixel: Pillow's coefficients (the filter stretched by the scale when shrinking, so it antialiases), its 22-bit fixed point, and its two passes, rows first, each rounded to 8 bits; a pass whose size doesn't change is skipped, as Pillow skips it. `Nearest` steps the source position as Pillow does. `Area` averages the source over each target pixel's footprint exactly, OpenCV's `INTER_AREA` when shrinking and Pillow's `BOX` at whole factors. One difference: Pillow resizes RGBA premultiplied by alpha, std.imgproc channel by channel. Other sample types are resampled in float64 with the same coefficients. `Mat3` and `Vec2` are std.matrix32's and std.vector32's ([[Language/Standard-library/Matrix]]: `m32.translation2d(v)`, `m32.rotation2d(a)`, `m32.scaling2d(v)`). The warps' `Bicubic` is Keys's cubic (a = −0.5) and `Lanczos3` the 6-tap windowed sinc; `Area` is bilinear there.

## Filters

| Function | What it gives |
| --- | --- |
| `kernel(w: int, h: int, data: [float32]) -> Kernel` | A kernel, row by row; its anchor is the middle (w / 2, h / 2) |
| `convolve<S>(img: Image<S>, k: Kernel, border: Border = Border.Reflect101) -> Image<S>` | Correlated with `k`, as OpenCV's `filter2D` (the kernel isn't flipped) |
| `convolve_sep<S>(img: Image<S>, kx: [float32], ky: [float32], border: Border = …) -> Image<S>` | `kx` along the rows, `ky` along the columns |
| `box_blur<S>(img: Image<S>, r: int, border: Border = …) -> Image<S>` | The mean of each (2r + 1)² square, by running sums: the same work for any `r` |
| `gaussian_blur<S>(img: Image<S>, sigma: float32, border: Border = …) -> Image<S>` | A Gaussian of `sigma`, separable, ceil(3σ) pixels to each side |
| `median(img: Image8, r: int, border: Border = Border.Replicate) -> Image8` | The median of each (2r + 1)² square, by Huang's sliding histogram: Pillow's `MedianFilter(2r + 1)` |
| `sharpen<S>(img: Image<S>, amount: float32 = 1.0f32, border: Border = …) -> Image<S>` | `v + amount·(4v − the four neighbours)` |
| `unsharp_mask<S>(img: Image<S>, sigma: float32, amount: float32 = 1.0f32, threshold: float32 = 0.0f32) -> Image<S>` | `v + amount·(v − blurred)` where the difference is at least `threshold` |
| `sobel<S>(img: Image<S>, dx: int, dy: int, size: int = 3, border: Border = …) -> ImageF` | OpenCV's Sobel derivative of order `dx`, `dy`, `size` 1, 3, 5 or 7, unscaled |
| `scharr<S>(img: Image<S>, dx: int, dy: int, border: Border = …) -> ImageF` | Scharr's 3 by 3 derivative |
| `laplacian<S>(img: Image<S>, size: int = 1, border: Border = …) -> ImageF` | `size` 1: the kernel [0 1 0; 1 −4 1; 0 1 0]; else the sum of the two second Sobel derivatives |
| `gradients<S>(img: Image<S>, border: Border = …) -> (ImageF, ImageF)` | The magnitude and the direction (radians, `atan2(gy, gx)`) of the 3 by 3 Sobel gradient |

Integer images are filtered in integers where the kernel allows: the derivatives exactly, `box_blur` exactly, `gaussian_blur` in fixed point with weights of 1/4096 a pass (within 1 of the exact result). The rest is float64 (float32 arithmetic is several times slower natively).

## Morphology

| Function | What it gives |
| --- | --- |
| `rect(w: int, h: int) -> Element`, `cross(w: int, h: int) -> Element`, `ellipse(w: int, h: int) -> Element` | Structuring elements (OpenCV's shapes), anchored at the middle |
| `erode(img: Image8, se: Element) -> Image8`, `dilate(img: Image8, se: Element) -> Image8` | The minimum, or maximum, under the element; pixels past the edge don't count. A rectangle whose sides add up to 8 or more goes by van Herk and Gil-Werman's algorithm (three comparisons a sample at any size: 33 ms at 1024 by 1024 for 5 by 5 as for 15 by 15), other elements by the runs of their rows |
| `morph(img: Image8, op: Morph, se: Element) -> Image8` | `Morph { Open, Close, Gradient, TopHat, BlackHat }`; the second step of an opening or a closing uses the element reflected, so an even-sized one opens too |

## Edges, corners, matching

| Function | What it gives |
| --- | --- |
| `canny(img: Image8, low: float32, high: float32) -> Image8` | Canny's edges (255) as OpenCV's `Canny` with an L2 gradient: 3 by 3 Sobel, non-maximum suppression in four directions, hysteresis with 8-connected pixels above `low` joined to one above `high`. It doesn't blur first |
| `harris<S>(img: Image<S>, block: int = 3, k: float32 = 0.04f32, border: Border = …) -> ImageF` | Harris's response `det M − k·trace(M)²`, M the structure tensor summed over `block` by `block`, the derivatives scaled so a full-scale step is 1 |
| `good_features<S>(img: Image<S>, max_corners: int, quality: float32 = 0.01f32, min_distance: float32 = 10.0f32, block: int = 3) -> [Vec2]` | Shi and Tomasi's corners, strongest first |
| `match_template<S>(img: Image<S>, t: Image<S>, method: Match = Match.Zncc) -> Result<ImageF, ImageError>` | The score at each position: `Ssd` (squared differences, 0 is a match), `Ncc` (OpenCV's TM_CCORR_NORMED), `Zncc` (TM_CCOEFF_NORMED, 1 is a match); the window sums come from summed-area tables, the cross term is direct (W·H·w·h products) |
| `min_max(f: ImageF, channel: int = 0) -> Extremes` | `Extremes { min, max, min_x, min_y, max_x, max_y }`, the first of each |
| `integral<S>(img: Image<S>, channel: int = 0) -> Integral` | A summed-area table; `.sum(r: Rect) -> float64` in four reads |

## Regions and quality

| Function | What it gives |
| --- | --- |
| `components(img: Image8, connectivity: int = 8) -> Components` | `Components { count, width, height, labels: [int32], stats: [Region] }` of the pixels that aren't 0: labels 1 to `count` in the order of each region's first pixel, `stats[l]` label l's `Region { area, bbox: Rect, centroid: Vec2 }`, `stats[0]` the background's (as OpenCV's); `c.mask(l)` a region's mask. Two passes over std.unionfind |
| `flood_fill(img: Image8, x: int, y: int, value: Color, tolerance: int = 0, connectivity: int = 4) -> Image8` | The pixels joined to the seed whose every channel is within `tolerance` of the seed's, set to `value` |
| `distance_transform(img: Image8) -> ImageF` | The exact Euclidean distance to the nearest 0 (Felzenszwalb and Huttenlocher); infinite without one |
| `mse<S>(a, b) -> Result<float64, ImageError>`, `psnr<S>(a, b) -> Result<float64, ImageError>` | The mean squared difference, and 10·log10(max² / mse) (infinite for equal images) |
| `ssim<S>(a, b) -> Result<float64, ImageError>` | Wang et al.'s structural similarity: an 11 by 11 Gaussian window of σ 1.5, K1 0.01, K2 0.03, the mean over the windows inside the image |

## Contours and shapes

```myla
import std.image as image
from std.image import Image8, Layout
import std.imgproc as imgproc
from std.imgproc import RetrievalMode
import std.float as fl

fun main() {
    // a ring with a dot in its hole, and a diagonal bar
    var img: Image8 = image.new(20, 12, Layout.Gray, 0u8)
    for y in 0..12 {
        for x in 0..20 {
            let d = (x - 5) * (x - 5) + (y - 5) * (y - 5)
            let ring = d <= 16 && d > 4 || d == 0
            let bar = x - y >= 9 && x - y <= 11 && y <= 10
            if ring || bar {
                img[(x, y, 0)] = 255u8
            }
        }
    }
    for c in imgproc.find_contours(img, RetrievalMode.Tree) {
        let kind = if c.hole { "hole" } else { "outer" }
        let r = imgproc.bounding_rect(c.points)
        print(f"{kind} in {c.parent}: {c.points.len()} pixels, area {imgproc.contour_area(c.points)}, {r.w}x{r.h} at ({r.x}, {r.y})")
    }
    for c in imgproc.find_contours(img, RetrievalMode.External) {
        let hull = imgproc.convex_hull(c.points)
        let box = imgproc.min_area_rect(c.points)
        print(f"hull of {hull.len()} corners, {imgproc.approx_poly(c.points, 1.0f32).len()} simplified, in {box.size.x:.2} by {box.size.y:.2} turned {box.angle:.1}")
    }
    let lines = imgproc.hough_lines(img, 1.0f32, (fl.PI / 180.0) as float32, 8)
    let l = lines[0]
    print(f"strongest line: rho {l.rho}, theta {(l.theta as float64).to_degrees():.0} degrees, {l.votes} votes")
}
// output:
// outer in -1: 20 pixels, area 38, 9x9 at (1, 1)
// hole in 0: 12 pixels, area 18, 7x7 at (2, 2)
// outer in 1: 1 pixels, area 0, 1x1 at (5, 5)
// outer in -1: 22 pixels, area 18, 11x11 at (9, 0)
// hull of 12 corners, 4 simplified, in 7.07 by 7.07 turned 45.0
// hull of 4 corners, 4 simplified, in 14.14 by 1.41 turned 45.0
// strongest line: rho -7, theta 136 degrees, 19 votes
```

| Function | What it gives |
| --- | --- |
| `find_contours(img: Image8, mode: RetrievalMode = RetrievalMode.Tree) -> [Contour]` | The borders of the regions of pixels that aren't 0 (8-connected, their holes 4-connected; pixels past the edge are 0), by Suzuki and Abe's border following: OpenCV's `findContours` with `CHAIN_APPROX_NONE`, the same points in the same order. `RetrievalMode { External, List, Tree }`: the outer borders no other border surrounds, every border flat, or every border with its parent. `Contour { points: [(int, int)], hole: bool, parent: int }`: every border pixel (x, y), from the first in raster order, an outer border counterclockwise on the screen (down its left side first), a hole's clockwise; `parent` the index of the border around it (-1 for none, and always outside `Tree`). For `Tree` the order is a depth-first walk with the later of two siblings first, else the borders found later first, as OpenCV's |
| `contour_area(points: [(int, int)], oriented: bool = false) -> float64` | The shoelace area; oriented, negative for an outer border and positive for a hole (as `contourArea`) |
| `arc_length(points, closed: bool = true) -> float64` | The perimeter, or the polyline's length |
| `bounding_rect(points) -> Rect` | The upright box, its `w` and `h` counting pixels |
| `convex_hull(points) -> [(int, int)]` | Andrew's monotone chain: the corners only, from the smallest (x, y), with a positive oriented area (OpenCV's orientation) |
| `approx_poly(points, epsilon: float32, closed: bool = true) -> [(int, int)]` | Ramer, Douglas and Peucker: no original point farther than `epsilon`; a closed one is split at the point farthest from the first and the one farthest from that, and starts at the former |
| `min_area_rect(points) -> RotatedRect` | The box of least area (the hull's sides as calipers); `RotatedRect { center: Vec2, size: Vec2, angle: float32 }`, `angle` in degrees from 0 up to 90, from the x axis toward y, `size.x` along it; `r.corners() -> [Vec2]` |
| `moments(points) -> Moments`, `image_moments(img: Image8, binary: bool = false) -> Moments` | A polygon's area moments (Green's theorem, the same either way round) or an image's (its first channel, or 1 where it isn't 0); `Moments` holds OpenCV's 24: `m00` … `m03`, the central `mu20` … `mu03` and the normalised `nu20` … `nu03`, float64 |
| `hu_moments(m: Moments) -> [float64]` | Hu's seven invariants |
| `point_in_polygon(points, p: Vec2) -> int`, `polygon_distance(points, p: Vec2) -> float64` | 1 inside, 0 on the border, -1 outside (even-odd); the signed distance to the border, positive inside (`pointPolygonTest`) |

## Lines and circles

| Function | What it gives |
| --- | --- |
| `hough_lines(img: Image8, rho: float32, theta: float32, threshold: int) -> [Line]` | The standard Hough transform of the pixels that aren't 0: `Line { rho, theta: float32, votes: int }` (x·cos θ + y·sin θ = ρ, θ from 0 to π in steps of `theta` radians, ρ in steps of `rho`), those with more than `threshold` votes that are local maxima, strongest first. It votes in float32 as OpenCV's `HoughLines` does, and gives its lines |
| `hough_segments(img: Image8, rho: float32, theta: float32, threshold: int, min_length: int, max_gap: int, seed: uint64 = 1u64) -> [Segment]` | The progressive probabilistic transform (OpenCV's `HoughLinesP`): pixels in a random order (std.random seeded by `seed`) vote until a line has `threshold`; its segment is walked both ways across gaps of up to `max_gap`, kept if it spans `min_length` in x or y, and its pixels removed. `Segment { x0, y0, x1, y1: int }` |
| `hough_circles(img: Image8, min_radius: int, max_radius: int, min_dist: float32, canny_high: float32 = 100.0f32, threshold: int = 20, support: float32 = 0.3f32) -> [Circle]` | The gradient method: Canny's edges of the gray vote along their gradient (both ways, every radius) for centres; a centre with more than `threshold` votes that is a local maximum, not within `min_dist` of one found before, gets the radius most edge pixels around it agree on, if they cover `support` of its circumference; centre and radius are refined by a least-squares circle (Kåsa's) through those pixels. `Circle { center: Vec2, radius: float32, votes: int }`, strongest first |

## Features

| Function | What it gives |
| --- | --- |
| `fast(img: Image8, threshold: int, nms: bool = true) -> [Keypoint]` | FAST-9 corners of the gray (Rosten and Drummond): nine contiguous pixels of the circle of radius 3 all brighter by more than `threshold`, or all darker; with `nms` those whose score beats their eight neighbours'. OpenCV's `FAST` (`TYPE_9_16`) exactly, with its score (the largest threshold at which the pixel stays a corner, minus 1) also without the suppression, where OpenCV gives 0. `Keypoint { pt: Vec2, score: float32, angle: float32, octave: int }`, row by row |
| `orb(img: Image8, n: int = 500) -> [Feature]` | ORB (Rublee et al.): FAST-9 (threshold 20) on eight levels each 1.2 times smaller, 20 pixels clear of each level's edge, the best by Harris's response (a 7 by 7 block), `n` shared by the levels' areas; each oriented by its intensity centroid (a disc of radius 15) and described by 256 comparisons of pairs of points of the level blurred (a 7 by 7 Gaussian of σ 2, in integers), the pattern turned by the orientation. `Feature { keypoint: Keypoint, descriptor: [uint64] }` (four words, test k in bit k % 64 of word k / 64), the keypoints in the image's pixels |
| `match_features(a: [Feature], b: [Feature], cross_check: bool = true) -> [FeatureMatch]` | Each of `a` with its nearest of `b` by the Hamming distance (the first of equals), brute force; with `cross_check` only mutual nearest. `FeatureMatch { a: int, b: int, distance: int }`, in `a`'s order |
| `hamming(a: [uint64], b: [uint64]) -> int` | The bits that differ |

ORB's pattern isn't OpenCV's learnt table: it is 256 pairs of points whose coordinates are drawn from a normal distribution of σ 6.2 (a fifth of the 31-pixel patch, as BRIEF draws them), rounded and held to -13..13, by Box and Muller's method over `random.seeded(0x4F5242)`. The descriptors are therefore not interchangeable with OpenCV's, though they behave alike: 300 features of a scene and of the scene turned 15° and scaled by 0.9 match, cross-checked, with more than 60% of the matches within 3 pixels of the true place (the burn test's case).

## Estimation and motion

| Function | What it gives |
| --- | --- |
| `find_homography(src: [Vec2], dst: [Vec2], threshold: float32 = 3.0f32, seed: uint64 = 1u64, max_iters: int = 2000) -> Option<(Mat3, [bool])>` | The homography taking `src` to `dst` despite outliers: RANSAC over samples of four (std.random seeded by `seed`, so the result is reproducible; at most `max_iters` samples, fewer once a 0.995 confidence is reached; collinear samples skipped), the one that takes the most points within `threshold` pixels of their match, refitted to those by the normalised direct linear transform (Hartley; the smallest eigenvector of AᵀA by Jacobi's rotations) until they stay the same. The matrix (bottom right 1, source to destination as `warp_perspective` takes it) and the inliers; None for fewer than four pairs, lists of different lengths or only degenerate samples |
| `find_affine(src, dst, threshold = 3.0f32, seed = 1u64, max_iters = 2000) -> Option<(Mat3, [bool])>` | The same for an affine map: samples of three, a least-squares refit |
| `optical_flow(prev: Image8, next: Image8, points: [Vec2], window: int = 21, levels: int = 3) -> Result<[(Vec2, bool)], ImageError>` | Bouguet's pyramidal Lucas and Kanade (as `calcOpticalFlowPyrLK`): coarse to fine over `levels` levels of `pyr_down` (fewer once a level is smaller than the window), each point's `window` by `window` neighbourhood (odd) matched by Newton steps (Scharr's derivatives of `prev`, bilinear samples, the border replicated; at most 30 steps a level, until a step is under 0.01 pixel). Each point's new place and whether it was tracked: false where its neighbourhood has too little texture (the structure tensor's smaller eigenvalue a pixel under OpenCV's `minEigThreshold`, 10⁻⁴ in its units) or the point left the image. `Err(Mismatch)` for images of different sizes |

## More filters

| Function | What it gives |
| --- | --- |
| `bilateral(img: Image8, d: int, sigma_color: float32, sigma_space: float32) -> Image8` | Tomasi and Manduchi's filter (OpenCV's `bilateralFilter`): the weighted mean of the disc of radius `d / 2` (round(1.5·σs) if `d` <= 0), each neighbour weighted by exp(-r² / 2σs²) and exp(-c² / 2σc²), c the sum of the colour channels' absolute differences; alpha takes the colours' weights; the border `Reflect101`. A gray image is filtered in fixed point (weights of 2⁻²⁰) |
| `watershed(img: Image8, markers: [int32]) -> [int32]` | Meyer's flooding (OpenCV's `watershed`): from the seeds (labels above 0; 0 unknown) over 4-connected pixels in the order of the colour difference (the largest channel difference) to the pixel each is reached from; each pixel its region's label, or -1 where regions meet. As OpenCV, the image's outermost pixels are -1 |
| `clahe(img: Image8, clip: float32 = 40.0f32, tiles: int = 8) -> Image8` | Contrast-limited adaptive histogram equalisation (OpenCV's `CLAHE`): a table a tile of `tiles` by `tiles`, its histogram clipped at `clip` times its mean bin (the excess spread evenly, `clip` 0 for none), each pixel the bilinear blend of its four nearest tiles' tables; an image whose size isn't a multiple of `tiles` is extended (`Reflect101`) for the tables, as OpenCV does. In float32 as OpenCV, so its results; each colour channel alike |

## How it is tested and how fast it is

`tests/burn/test_imgproc.py` runs 108 cases natively against references independent of the module, vendored once by `python3 -m tests.burn.test_imgproc --vendor` (Pillow and numpy, which the test itself doesn't need): Pillow's `convert`, `ImageOps.invert`, `histogram`, `ImageChops.difference`, `resize` with each filter (gray and RGB, shrinking and enlarging), `BOX`, `MedianFilter`, `MinFilter` and `MaxFilter`, which std.imgproc matches exactly; `colorsys`; `numpy.pad` (each border, exactly) and `numpy.linalg.solve`; and textbook numpy for the rest. All but four cases match exactly: `resize` with `Area` at a fraction and `gaussian_blur` of an `Image8` (gray and RGB) are within 1 (fixed point), and the float `resize` within 10⁻⁷.

Natively at 1024 by 1024 gray (x86-64, `myla build`, 2026-11-25; the best of five), beside Pillow 13 on the same machine:

| Work | std.imgproc | Pillow |
| --- | --- | --- |
| `gray` of RGB | 3.7 ms | 0.64 ms |
| `resize` to 640×480: `Nearest`, `Bilinear`, `Bicubic`, `Area`, `Lanczos3` | 0.8, 12.6, 15.3, 10.1, 22.1 ms | 0.08, 2.3, 3.7, 1.5 (`BOX`), 5.4 ms |
| `resize` of RGB, `Bilinear` | 35.8 ms | 5.5 ms |
| `gaussian_blur` σ 2 | 47 ms | 9.0 ms (`GaussianBlur(2)`, box approximations) |
| `box_blur` r 2 | 27 ms | 4.0 ms |
| `median` r 2 | 102 ms | 330 ms (`MedianFilter(5)`) |
| `erode` 5 by 5 | 33 ms | 228 ms (`MinFilter(5)`) |
| `sobel` | 33 ms | |
| `canny` | 37 ms | |
| `components` of a threshold | 20 ms | |
| `distance_transform` | 87 ms | |
| `warp_affine` (a turn) | 59 ms | 10 ms (`rotate(17, BILINEAR)`) |

C with SIMD and no bounds checks is 4 to 10 times faster per pixel at the regular kernels; Huang's median and the run-based morphology are faster than Pillow's rank filters.

Tier B's `tests/burn/test_imgproc_b.py` runs 39 cases natively against references vendored once by `python -m tests.burn.test_imgproc_b --vendor` with OpenCV 5.1 (`opencv-python-headless` and numpy, which the test doesn't need), or against ground truth where std.imgproc's method is its own. OpenCV's results are matched exactly by `find_contours` (each mode, the nesting, every point in order), `bounding_rect`, `convex_hull` (up to the start), `hough_lines` (lines, angles and votes), `fast` (keypoints and scores), `erode` and `dilate` with large rectangles, `watershed` and `clahe`; within 10⁻¹² to 10⁻⁶ relative by `contour_area`, `arc_length`, both `moments`, `hu_moments` and `polygon_distance`; `min_area_rect`'s area within 10⁻³, its box OpenCV's or another of the same area holding every point; `bilateral` within 1. Ground truth: `approx_poly` finds the corners of four polygons within 1.5 pixels; `hough_segments` gives only segments within 3 pixels of five drawn lines and covers 80% of each; `hough_circles` finds three discs at subpixel centres within 1 pixel, their radii within 1; `orb` as above; `find_homography` and `find_affine` of 1000 pairs, half of them outliers, find exactly the inliers and a map within 0.01 pixel of the true one (0.25 with noise of ±0.5); `optical_flow` follows a smooth scene's subpixel move (2.3, -1.6) within 0.05 pixel at 54 points (0.1 with a 9 by 9 window).

Natively at 1024 by 1024 gray (x86-64, `myla build`, 2026-11-25, the best of five, with five other jobs on the machine's four cores), beside OpenCV 5.1 on one thread:

| Work | std.imgproc | OpenCV |
| --- | --- | --- |
| `find_contours` of a threshold (8,900 borders) | 8.0 ms | 12 ms |
| `hough_lines` of Canny's edges (1°, 36 lines) | 48 ms | 8.6 ms |
| `fast` (threshold 20, 800 corners) | 11 ms | 0.33 ms |
| `orb`, 500 features | 124 ms | 9.0 ms |
| `find_homography`, 1000 pairs, 50% outliers | 3.8 ms | 1.7 ms |
| `optical_flow`, 200 points, window 21, 3 levels | 42 ms | 4.8 ms |
| `bilateral`, d 9 | 134 ms | 25 ms |
| `erode` 15 by 15 | 33 ms | 0.44 ms |
| `clahe` | 44 ms | 4.4 ms |
| `watershed`, 64 seeds | 97 ms | 58 ms |
