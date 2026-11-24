---
id: MYLA-930
title: "Images, vision and fonts in std: the owner's decisions and the umbrella"
type: chore
status: in-progress
priority: medium
labels: [stdlib, images, design]
---
The umbrella of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]: image codecs (PNG, JPEG, GIF, TIFF, BMP, PNM, QOI), image processing and computer vision (std.imgproc), 2D drawing (std.draw) and TrueType fonts (std.font), in Myla, for the GUI ([[MYLA-63]]) and for programs before it. The page has the proposed feature set and API, the measurements behind it, and the plan. Its tasks are [[MYLA-931]] to [[MYLA-945]], all in `backlog` until these questions are decided.

## Open questions for the owner

Each has the page's recommendation first. The owner accepted every recommendation on 2026-11-24: D311.

- [x] **std or packages:** in std, as portable computation like std.compress (the GUI, windows and display stay out); or official packages, which [[MYLA-245]] hasn't designed yet. Updates [[Project/Standard-library-roadmap#Left out]] either way
- [x] **Image type:** a generic `Image<S: Sample>` over `uint8`, `uint16`, `float32` with the aliases `Image8`, `Image16`, `ImageF`; or generated twins as D201 did for the vectors
- [x] **Storage:** one interleaved row-major `[S]` and a runtime `Layout` (Gray, GrayAlpha, Rgb, Rgba); or a list of pixel structs (2.3 times slower natively, measured)
- [x] **Errors:** one `ImageError` (a bare enum, D168) for every codec, std.imageio and std.imgproc; or one per module
- [x] **Style:** methods for what belongs to an image, free functions chained by `|>` for algorithms, a `Canvas` with `var self` methods for drawing
- [x] **Fixtures:** freely licensed conformance files vendored under `tests/burn/data/`, the expected pixels made once with Pillow and committed (CI needs nothing installed); or Pillow as a test dependency
- [x] **JPEG exactness:** bit-identical to libjpeg's default decode (islow IDCT, fancy upsampling), so tests compare exactly; or a faster IDCT and a tolerance
- [x] **Fonts:** a small built-in bitmap font of our own design, TrueType from files, an OFL font's subset vendored for the tests

## Steps

- [x] The questions decided, the decision recorded, the page updated to match (D311)
- [ ] The tasks moved to `todo` in the page's order, step 1 first (three waves of parallel lanes, below)
- [ ] After std.png and std.jpeg: the embedded library's growth measured, before the rest goes ahead
