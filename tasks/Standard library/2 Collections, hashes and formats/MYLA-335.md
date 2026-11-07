---
id: MYLA-335
title: "std.regex: regular expressions in linear time"
type: feature
status: backlog
priority: medium
labels: [stdlib, strings, regex, wave-2]
---
Wave 2 of [[Project/Standard-library-roadmap]], roadmap #59. RE2's model: a pattern compiles to an automaton (Thompson NFA with a lazily built DFA), matching in time linear in the input, no backreferences and no lookaround. A longer task with no dependencies, so it can start in any wave.

- **Owns:** `lib/std/regex.my`, `docs/Language/Standard-library/Regex.md`
- **Needs:** nothing; it can start as soon as its wave does
- Work by the lane rules of [[Project/Standard-library-roadmap#Working in parallel]]: touch only the files this task owns, plus one row of the index table on [[Language/Standard-library]]; don't commit seeds or `selfhost/embedded_std.my`.

- [ ] The syntax: literals, `.`, classes (`[a-z]`, `\d`, `\w`, `\s`), anchors, groups, alternation, `*` `+` `?` `{m,n}`, lazy forms
- [ ] `compile`, `is_match`, `find`, `find_all`, `captures`, `replace`, `split`
- [ ] A pathological pattern (`(a*)*b` on 10,000 `a`s) takes linear time
- [ ] Checked against a corpus of patterns and inputs whose expected results come from RE2's or Go's tests
- [ ] `#test` cases on every public function that has values to compare, test functions for the generic ones (D162), passing interpreted and with `--native`
- [ ] Its page below [[Language/Standard-library]], with a doc block that runs
