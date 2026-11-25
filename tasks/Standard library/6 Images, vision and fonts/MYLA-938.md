---
id: MYLA-938
title: "std.gif: frames, animation and encoding"
type: feature
status: in-progress
priority: low
labels: [stdlib, images, gif]
---
Step 3 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]].

- **Owns:** `lib/std/gif.my`, `docs/Language/Standard-library/Gif.md`
- **Needs:** [[MYLA-933]], [[MYLA-932]] (LZW), [[MYLA-945]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `decode` (the first frame) and `decode_all` (an `Animation` of `Frame`s): GIF87a and GIF89a, global and local palettes, transparency, interlacing, delays, disposal, the NETSCAPE2.0 loop count; `max_pixels` over all frames together
- [ ] `composite`: every frame as shown, the three disposal methods applied, equal to Pillow's frames of the corpus
- [ ] `encode` and `encode_all` through `image.quantize`; transparency kept; frames that change only part of the canvas written as their rectangle
- [ ] Pillow reads every output with the same frames, delays and loop count
- [ ] Its corpus and fuzz cases in [[MYLA-945]]'s harness: truncations and seeded mutations are `Ok` or `Err`, never a runtime error, natively plain and `--checked`
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
