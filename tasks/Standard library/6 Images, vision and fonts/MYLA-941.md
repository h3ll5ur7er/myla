---
id: MYLA-941
title: "std.imgproc, tier A: colour, geometry, filters, morphology, edges, regions"
type: feature
status: in-progress
priority: medium
labels: [stdlib, images, vision]
---
Step 4 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]: what most image programs reach for. Tier B is [[MYLA-944]].

- **Owns:** `lib/std/imgproc.my`, `docs/Language/Standard-library/Imgproc.md`
- **Needs:** [[MYLA-933]]; std.vector32, std.matrix32, std.unionfind as they are
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] Colour and point operations: `gray`, `to_rgb`, HSV, linear and sRGB, `invert`, `adjust`, `gamma`, `lut`, `threshold`, `otsu`, `adaptive_threshold`, `in_range`, `histogram`, `equalize`, `normalize`, `abs_diff`, `blend`, `apply_mask`
- [ ] Geometry: `resize` with five filters, `thumbnail`, `rotate`, `warp_affine`, `warp_perspective`, `affine_from`, `perspective_from`, `pad`, `pyr_down`, `pyr_up`; `Border`
- [ ] Filters: `convolve`, `convolve_sep`, `box_blur` (running sums), `gaussian_blur` (separable), `median` (sliding histogram), `sharpen`, `unsharp_mask`, `sobel`, `scharr`, `laplacian`, `gradients`
- [ ] Morphology: `erode`, `dilate`, `morph`, `rect`, `cross`, `ellipse`
- [ ] Edges, corners, matching: `canny`, `harris`, `good_features`, `match_template`, `min_max`, `integral`
- [ ] Regions: `components` with region statistics, `flood_fill`, `distance_transform`
- [ ] Quality: `mse`, `psnr`, `ssim`
- [ ] A reference for each function, independent of the code: Pillow's where it has one (resize filters, Gaussian blur, rank filters, histograms) through vendored outputs, otherwise the textbook formula in a short Python reference over a few small images, with the tolerance stated per function
- [ ] Measured natively at 1 MP: `resize` (each filter), `gaussian_blur` at sigma 2, `median` of radius 2, `canny`, `components`, beside Pillow where it has them
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
