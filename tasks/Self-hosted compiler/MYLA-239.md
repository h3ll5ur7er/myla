---
id: MYLA-239
title: "Named #test cases: a trailing comment names the case"
type: improvement
status: done
priority: low
labels: [testing, attributes]
---
The owner's request (2026-11-02): `#test(args)[expected] // my sample test` names the case, and `myla test` reports it as `sometest #5 (my sample test)`; a case without a comment is reported as before.

- [x] The comment after a `#test` attribute reaches the attribute (lexer, parser, AST)
- [x] `myla test` shows the name on PASS and FAIL lines
- [x] A burn test; [[Language/Attributes-and-testing]] and the myla skill

## Evidence

- **How.**
  - The lexer keeps the text of a `//` comment that follows code on its line, and hands it over in the suffix of that line's NEWLINE token. The canonical token dump prints no suffix for a newline, so the lexer gates see no change.
  - The parser gives a `#test` attribute the comment that ends its line as its `label` (the new `Attribute.label`).
  - `myla test` (`run_test_cases` in [[selfhost/interp.my]]) reports `name #n (label)`.
- **Test first.** `tests/burn/test_test_names.py`: an unnamed case; a named one; a named failing one (`FAIL  add #3 (wrong on purpose): expected 5, got 4`; the spaces around the name are trimmed); a method's case; a comment after `#derive`, which names nothing. Before the change the names were missing; now the output is exact.
- **An existing comment becomes a name.** `examples/attributes.my` already had a comment after a case (`// 255 + 1 wraps to 0 in a uint8`), which now shows as its name. The command-parity corpus of `test_selfhost_cli` leaves case names out when it compares with the recorded Python CLI, which had none.
- **Docs.** [[Language/Attributes-and-testing]] and the myla skill. The burn suite passes, and the bootstrap reaches its fixed point with the new seed.

