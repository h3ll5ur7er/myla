---
id: MYLA-318
title: "Small language gaps from Advent of Code"
type: improvement
status: backlog
priority: low
labels: [language, stdlib]
---
Found by Advent of Code ([[Project/AoC-2015-2021]], F9). None of these blocked anything. Each cost lines in many solutions. The counts are grep-based across the 175 solutions, so they're approximate. The messages are from master `d5d80bc`.

| Gap | How often | Today |
| --- | --- | --- |
| `for c in s` over a `str` | up to 66 `while` loops | "`for ... in` requires a list or map, found 'str'"; `for c in s.chars()` works, at the cost of a list |
| A list of n equal values | about 51 push loops | no function; a candidate for the roadmap's list helpers |
| A set type | 37 `[K: bool]` maps | on [[Project/Standard-library-roadmap]] |
| A map lookup with a default | 14 of 29 uses of `get` | `get(m, k)` gives an `Option`; `m.get_or(k, d)` or `get(m, k) ?? d` |
| `parse_int` always needs unwrapping | 12 uses | wants a `?`-able `Result` with a reason, or an `unwrap_or` on `Option` |
| `<` on strings | 1 helper, `str_less` | "comparison requires numeric or char operands"; byte-wise ordering would do |
| `'p' - 'a'` | rare | "operator '-' requires integer operands"; `s[i] - 'a'` works, as the literal fits a byte there |
| `#test` on generic functions | every generic helper | excluded by D116, and left out on purpose by [[MYLA-303]]; tested through wrappers |

- [ ] `for` over a `str`: by `char` (as `chars()`) or by byte, a decision in passing
- [ ] `<`, `<=`, `>`, `>=` on strings (byte-wise, as `list_dir` sorts)
- [ ] `char - char` as an `int32` (and `char + int`), or the reason it stays out
- [ ] The library ones (a list of n values, a set, a lookup with a default, `unwrap_or`) through [[Project/Standard-library-roadmap]]
