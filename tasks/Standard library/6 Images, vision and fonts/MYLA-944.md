---
id: MYLA-944
title: "std.imgproc, tier B: contours, Hough, features, homographies, optical flow"
type: feature
status: in-progress
priority: low
labels: [stdlib, images, vision]
---
Step 6 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]: computer vision beyond filters. Optional; each part may become a task of its own when it starts.

- **Owns:** the tier-B parts of `lib/std/imgproc.my` and its page
- **Needs:** [[MYLA-941]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] Contours and shapes: `find_contours` (Suzuki–Abe, with the hierarchy), `contour_area`, `arc_length`, `bounding_rect`, `min_area_rect`, `convex_hull`, `approx_poly`, `moments` and Hu's invariants, `point_in_polygon`
- [ ] Hough: `hough_lines`, `hough_segments`, `hough_circles`
- [ ] Features: `fast`, `orb`, `match_features`
- [ ] Estimation: `find_homography` (RANSAC, seeded, and a DLT refit), `find_affine`
- [ ] `optical_flow` (pyramidal Lucas–Kanade)
- [ ] `bilateral`, van Herk–Gil-Werman morphology, `watershed`, CLAHE
- [ ] An example: a photo of a page, its corners found, the page warped flat
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
