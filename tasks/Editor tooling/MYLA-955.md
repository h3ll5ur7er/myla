---
id: MYLA-955
title: "The language server's resolver: import aliases, parameter defaults and `_`"
type: bug
status: review
priority: medium
labels: [lsp, editor]
---
Found by the full suite after D313's image modules merged: `tests.burn.test_lsp.TestResolutionCorpus` failed on eight of them (draw, font, gif, image, imgproc, jpeg, png, tiff). Three gaps in [[tools/lsp/resolve.my]], none of them the modules' fault:

1. `for _ in 0..n` declared a local `_`, so `_` counted as a name and every `_` pattern after it looked unresolved. `_` binds nothing: `declare_detail` now skips it.
2. An import's alias (`import std.image as image`) was no use of anything, so go-to-definition and the corpus check found nothing there; it showed only where the alias is also a field's name (`Mask.image`). The alias is now a use of its module (the identifier after the path's segments: the resolver's tokens are identifiers only).
3. Parameter defaults (`mode: Threshold = Threshold.Binary`, `opts: LayoutOptions = layout_options()`) were never visited. They are now resolved before the parameters are declared, as the caller's expression they are.

- [x] `test_aliases_defaults_and_wildcards` in `tests/burn/test_lsp.py`: all three on one small file
- [x] `python3 -m unittest tests.burn.test_lsp`: 171 tests OK (2026-11-25); the corpus check over every std module, example and tool passes again
