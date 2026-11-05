---
id: MYLA-277
title: "Number formatting in `format` and f-strings: width, alignment, precision (`{x:>8.3}`)"
type: feature
status: backlog
priority: high
labels: [language, stdlib, formatting]
---
Decided by D113 ([[MYLA-211]]), split off [[MYLA-189]] so it is on the menu of its own (the owner, 2026-11-05: for the near future, not at once). D58 left format specs out of v0.5 only; they were never dropped.

```myla
let pi = 3.14159265
print(f"{pi:.2}")          // 3.14
print(f"[{42:>6}]")        // [    42]
print(f"[{42:<6}]")        // [42    ]
print(f"[{42:^6}]")        // [  42  ]
print(f"{7:03}")           // 007
print(f"{255:x} {255:b}")  // ff 11111111 (if the round takes types too)
```

A short design round first, to settle the spec's grammar, recorded on [[Language/Collections-and-strings]] and [[Language/Standard-library]]:
- **Width and alignment:** `>`, `<`, `^`; a fill character (`{x:*>8}`?).
- **Precision for floats:** fixed digits after the point, rounded half to even as the shortest form is today ([[Architecture/Native-backend]], "Float formatting").
- **Zero padding and signs:** `{x:+}`.
- **Whether hexadecimal, binary and octal belong in it** (`{x:x}`, `{x:b}`, `{x:o}`).
- **What a spec on a string, a `char`, a `bool` or a struct does:** width only, or an error.
- **Errors:** a malformed spec in an f-string is a parse or type error at its position, since the spec is known at compile time. In a `format` call with a constant string, the same.

Then:
- [ ] The decision and the pages
- [ ] Lexer (the spec after `:` inside a hole, kept apart from `::` and from a map literal's `:` inside a hole) and checker (the spec against the value's type)
- [ ] Std code: the formatting in Myla (`std.num`), shared by the interpreter and every backend, so the output is byte-identical everywhere
- [ ] Tests: parity programs, the error corpus, the tree-sitter grammar's f-string rule

## Proposal for the design round (2026-11-05, for the owner; nothing decided)

A hole is `{expression:spec}`, the spec fixed in the source (an f-string, or a constant `format` string), so it is checked at compile time against the value's type.

| Question | Options | Recommendation | Example |
| --- | --- | --- | --- |
| The spec's grammar | A: Rust's order `[[fill]align][sign][0][width][.precision][kind]`; B: Python's (the same plus `,` grouping and `%`); C: width, alignment and precision only | **A**, without Rust's `#` forms and run-time widths (`{x:>w$}`) for now | `{x:*>8.2}` |
| Alignment and fill | default right for numbers, left for text (Rust, Python); or always right | **Rust's defaults**; any one `char` as fill before `<`, `>`, `^` | `f"[{42:<6}]"` → `[42    ]`, `f"[{"ab":^6}]"` → `[  ab  ]`, `f"{7:*>4}"` → `***7` |
| Width counts | bytes, or Unicode scalars | **scalars** (as `chars(s)` counts) | `f"[{"λ":>3}]"` → `[  λ]` |
| Precision on floats | rounded on the exact binary value (Rust, C), or on the shortest digits | **the exact value** (correctly rounded, ties to even only on exact ties): the only rule that is the same everywhere without surprises at the next digit | `f"{2.675:.2}"` → `2.67` (2.675 is 2.67499… in binary), `f"{0.125:.2}"` → `0.12` |
| Precision elsewhere | ignored (Rust on integers), truncation (Rust and Python on strings), or an error | **an error** on anything but floats: one meaning per spec | `f"{5:.2}"` → type error |
| Signs and zeros | `+` forces a sign; `0` pads after the sign | **both, numbers only** | `f"{7:+}"` → `+7`, `f"{-7:04}"` → `-007` |
| Integer kinds | `x`, `X`, `b`, `o` now; `e` for floats later | **`x X b o` on integers**, two's complement of the type's width for a negative signed value (Rust) | `f"{255:x} {255:b} {-1i8:x}"` → `ff 11111111 ff` |
| Types a spec takes | numbers only; numbers, `str`, `char`, `bool` | **width, fill and alignment on all four**; sign, `0`, precision and kinds as above | `f"{true:>6}"` → `  true` |
| A non-constant `format` string | specs read at run time (an error there), or none | **none**: a spec needs a constant string, so every spec is checked before the program runs | `format(s, x)` with `s` a variable: specs not read, `{` `}` as today |
| Where it is built | the lexer splits the hole at its last top-level `:` (not inside `[ ]`, `( )`, `{ }` or a string, so `{m["a"]:>4}` and `{[1: 2].len()}` work); the formatting is Myla in `std.num` | as said | |

The checker's errors name the spec's position: `type error: the format spec '.2' needs a float, found 'int32'`.
