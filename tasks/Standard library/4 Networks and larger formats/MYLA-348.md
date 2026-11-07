---
id: MYLA-348
title: "std.xml: a non-validating parser and writer"
type: feature
status: backlog
priority: low
labels: [stdlib, formats, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #56. Elements, attributes, text, entities, CDATA, comments and processing instructions; no DTD and no namespaces at first.

- **Owns:** `lib/std/xml.my`, `docs/Language/Standard-library/Xml.md`
- **Needs:** [[MYLA-341]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] A tree parser and a pull reader
- [ ] A writer with escaping
- [ ] Checked against the well-formedness part of the W3C conformance suite
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
