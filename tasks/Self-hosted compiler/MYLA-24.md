---
id: MYLA-24
title: format() with a char or float argument segfaults
type: bug
status: backlog
priority: medium
labels: [selfhost, codegen, strings]
---
`render_arg` in [[selfhost/codegen.my]] (around line 2586) has no `TChar` or `TFloat` arm, so the value is used as a string pointer. `format("{}", 'a')` and `f"{c}"` with a `char` crash.

## Done when

- [ ] `TChar` renders through `__char_to_str` (as `print` already does)
- [ ] `TFloat` renders once float codegen exists ([[MYLA-29]])
- [ ] Differential test
