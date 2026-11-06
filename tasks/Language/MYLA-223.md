---
id: MYLA-223
title: "Compound assignment"
type: feature
status: done
priority: medium
labels: [language, ergonomics]
---
D104 (2) ([[MYLA-215]]): `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=`, `>>=` mean `x = x op y`, with the place (`a[i()].f`) evaluated once; operator overloading applies through the operator's trait. Shifts exist (D44) and `>>` already means a shift on integers and composition on functions (D24), so `<<=` and `>>=` follow (`f >>= g` composes); the owner kept them on 2026-11-02.

- [x] Lexer, parser, grammar; checker (the target must be a `var` place, the operator defined for its type); lowering with the place's indices computed once
- [x] A test that an index expression with a side effect runs once; error-corpus files
- [x] [[Language/Statements]] ("There is no compound assignment yet" goes), the skill and `AGENTS.md` ("no `+=`")

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).

## Evidence

- **How.** The parser desugars `place op= value` into `place = place op value` ([[selfhost/parser.my]]: `compound_ahead`, `compound_assign`, `hoisted`).
  - The compound operators are touching token pairs (`+` `=`, … `<` `<=`, `>` `>=`), so the lexer is unchanged; the binary operators' loops stop in front of one.
  - An index that isn't a name or a literal is computed into a hidden `let` first, both inside `if true { … }`, so the place is evaluated once.
  - The checker (a `var` place, the operator defined for the type, operator traits), the D95 walk, the interpreter and the lowering then see an ordinary assignment, with nothing added to them.
- **Grammar.** [[grammar/myla.ebnf]] and [[Language/Grammar]]: `assignment = place ( "=" | compound_op ) expression`, the compound operators `@adjacent`. The tree-sitter grammar is regenerated.
- **Test first.** `tests/burn/test_compound_assignment.py`:
  - every operator on integers;
  - a float, a string, list elements, a struct field and a map value;
  - a struct's `Add`, and `>>=` composing two functions;
  - `int64` `<<= 40`;
  - `xs[pick(2)] *= 10` and nested `cells[pick(0)].items[pick(1)] -= 6`, each `pick` printed once.

  The output is the same in the interpreter and natively. Errors: a `let` target, `-=` on strings, a non-place, a type mismatch. Before the change the program didn't parse ("expected an expression, found '='").
- **Error corpus.** `type_compound_assign_to_let.my` and `parse_compound_assign_target.my`. The four gates that compare every corpus file with the Python recordings (checker, lexer, parser, codegen diagnostics) now leave out files added since; `test_error_corpus` holds those to the self-hosted CLI.
- **Docs.** [[Language/Statements]] (with a tested example), `AGENTS.md` and the myla skill. The burn suite passes, and the bootstrap reaches its fixed point with the new seed.

## Evidence (review 2026-11-06)

- [x] `ys[^3] += 5` (reopened by [[Project/Review-2026-11]]): the compound-assignment desugar hoists the operand of `^`, not the `^` (`hoisted` in [[selfhost/parser.my]]); `test_compound_assignment` has the case (`ys[^1] += 5`, `ys[^pick(3)] *= 2`)
