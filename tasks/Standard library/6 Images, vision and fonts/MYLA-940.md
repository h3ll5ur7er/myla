---
id: MYLA-940
title: "std.imageio: load and save any supported format"
type: feature
status: backlog
priority: medium
labels: [stdlib, images]
---
Step 4 of [[Project/Standard-library-roadmap/Images-vision-and-fonts]]: the module most programs import.

- **Owns:** `lib/std/imageio.my`, `docs/Language/Standard-library/Imageio.md`
- **Needs:** [[MYLA-934]], [[MYLA-935]], [[MYLA-936]]; [[MYLA-938]] and [[MYLA-939]] as they land
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Format`, `sniff` (magic bytes), `format_of` (extension, case-insensitive)
- [ ] `info`, `decode`, `encode`, `load` (EXIF orientation applied), `save` (format from the extension, `quality` for JPEG); file errors as `ImageError.Io`
- [ ] A file whose extension and contents disagree is read by its contents
- [ ] Measured: the check time of a program that imports std.imageio, against one that imports std.png alone
- [ ] `#test` cases on every public function that has values to compare (images up to about 16×16), test functions for the generic ones (D162), passing interpreted and `--native`, and on aarch64 (qemu) and wasm32 (Node)
- [ ] Its page below [[Language/Standard-library]] with a doc block that runs, the skill's `reference/stdlib.md`, and an example in `examples/`, registered
