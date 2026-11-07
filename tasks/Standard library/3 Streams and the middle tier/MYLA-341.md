---
id: MYLA-341
title: "std.text: a scanner and text layout"
type: feature
status: backlog
priority: medium
labels: [stdlib, strings, parsing, wave-3]
---
Wave 3 of [[Project/Standard-library-roadmap]], roadmap #8, #9. What hand-written parsers and reports need beyond `split`.

- **Owns:** `lib/std/text.my`, `docs/Language/Standard-library/Text.md`
- **Needs:** [[MYLA-321]], [[MYLA-322]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] `Scanner`: `peek`, `next`, `take_while`, `skip_space`, `expect`, `int`, `ident`, the position for errors
- [ ] `ints(line)`: every integer in a line, signs included
- [ ] Word wrap, aligned columns, indent and dedent
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
