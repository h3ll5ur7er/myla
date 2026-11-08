---
id: MYLA-390
title: "Small gaps from wave 4: for (k, v) in pairs, slicing bytes that aren't UTF-8"
type: improvement
status: backlog
priority: low
labels: [language, strings]
---
Found by the wave 4 lanes ([[MYLA-348]], [[MYLA-352]], [[MYLA-349]]).

- [ ] `for (k, v) in pairs` doesn't parse ("expected loop variable name"); two lanes wrote `for kv in pairs { let (k, v) = kv }`. A tuple pattern in a `for` head (and maybe any irrefutable pattern), in the grammar, the checker and every runner
- [ ] `s[a:b]` is "a slice bound inside a character" when `b` lands on a byte of the form `10xxxxxx` even where the bytes around it aren't a well-formed sequence. Strings are bytes (D164): decide whether the check should only refuse a bound inside a *well-formed* character, and say so on [[Language/Collections-and-strings]]. `std.xml` copies through `StringBuilder.append(s, a, b)` instead
- [ ] `StringBuilder` has no `append_char`
