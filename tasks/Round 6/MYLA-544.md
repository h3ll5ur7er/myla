---
id: MYLA-544
title: "R2 The checker: `x.format(spec)` on a builtin, a negated char literal, literals beside typed operands"
type: bug
status: todo
priority: medium
labels: [checker, round-6]
---
Work package R2 of [[Project/Review-2026-11-12]]. Files: `selfhost/checker.my`. Same lane as [[MYLA-417]] and [[MYLA-394]] (reopened) and [[MYLA-538]] (raised to `high`).

- [ ] **`x.format(spec)` on `T: Format` with a builtin `T`** checks, and then the interpreter fails inside itself and `myla build` says `can't be lowered`. A user type works, and so does `f"{x}"` (`repro-r5/checker/bug5_format_method_on_builtin.my`):

  ```myla
  fun show<T: Format>(x: T) -> str { return x.format("") }
  fun main() {
      print(show(5))
  }
  ```
- [ ] `let v: uint8 = -'a'` is accepted and prints 159 (`bug4_neg_char_literal_unsigned.my`)
- [ ] A literal left of a typed operand is typed differently from one on its right (`gap1_literal_left_of_typed_operand.my`)
- [ ] The expected type isn't passed through an overloaded operator (`gap2_expected_type_through_operator.my`, [[MYLA-367]])
- [ ] The hint for a static method called on a value (`low1_static_on_value_hint.my`)
- [ ] `docs/Language/Lexical-structure.md`, line 107: "`128i8` is therefore accepted and wraps to -128" is false now (it is a type error, while `-128i8` works); line 106's "there are no negative literals" should say that a negated literal is checked as the value it denotes
