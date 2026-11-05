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
