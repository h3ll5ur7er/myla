---
id: MYLA-349
title: "std.yaml: the safe subset"
type: feature
status: backlog
priority: low
labels: [stdlib, formats, wave-4]
---
Wave 4 of [[Project/Standard-library-roadmap]], roadmap #57. Block and flow maps and lists, scalars (plain, quoted, multi-line), comments; no anchors, no tags, no multiple documents at first. Values are a `Yaml` enum like `Json`.

- **Owns:** `lib/std/yaml.my`, `docs/Language/Standard-library/Yaml.md`
- **Needs:** [[MYLA-341]]
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] The parser and a writer
- [ ] Checked against the cases of the YAML test suite that the subset covers
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
