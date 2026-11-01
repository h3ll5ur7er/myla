---
id: MYLA-184
title: "The #test convention in selfhost/: 1,164 of 1,259 value-returning functions have none"
type: chore
status: todo
priority: low
labels: [selfhost, tests, docs]
---
Found by the October 2026 review of the whole project ([[Project/Review-2026-10]]). [[Development/Conventions]], the `myla` skill and [[Architecture/Self-hosted-compiler]] say every value-returning function in `selfhost/` carries `#test` cases; `tests/burn/test_examples_tests.py` enforces it only for `examples/`. Counted on 2026-10-31: lexer 21 of 21 untested, parser 103 of 108, checker 296 of 299, lower 85 of 85, interp 180 of 183, codegen 182 of 194. The tests that exist are meaningful.


Also a decision question from the review's §11.10, tracked with the others in `Review decisions/` ([[MYLA-201]] to [[MYLA-217]]).

## Options

- **A. Enforce it for `selfhost/`**: a burn test like the one for `examples/`, and some 1,160 functions to cover, many of which need a whole AST or IR to be called.
- **B. Restate it**: "every function in `examples/` and the standard library; in the self-hosted compiler, functions that can be tested in isolation", with the three places that state it agreeing.
- **C. B plus a ratchet**: a burn test that counts the `selfhost/` functions with `#test` cases and fails when the count drops, so new pure helpers come with cases.

## Recommendation

**C.** The convention becomes true as written, and coverage can only grow; starting with the pure helpers of `ir.my`, `lower.my` and `util.my`.

## Decision

**D109 (2026-11-01).** The owner: "soft enforce >80 % coverage". A burn test reports the share of value-returning functions with `#test` cases per module and overall, and warns without failing while the overall share is below 80 %.

- [x] Decided (D109): at least 80 %, softly enforced; it used to read: enforce the convention for `selfhost/` (and start with the pure helpers of `ir.my`, `lower.my`, `util.my`), or restate it as "the examples, and the self-hosted compiler where a function is testable in isolation"
## Approach

The owner's point: a case is only an input and an output, and the toolchains already compute both, so cases can be generated rather than written. Measured on 2026-11-01 (1,272 value-returning functions in `selfhost/`, 96 with cases):

| Kind | Functions | Generated cases |
| --- | --- | --- |
| Free function, simple inputs (numbers, `str`, `char`, `bool`, lists and options of them) | 267 | Directly: argument and result literals |
| Free function taking compiler data (AST, IR, tokens, types) | 415 | Where the values print as Myla expressions of bounded size (struct literals, enum constructors), or built by a helper call (`#test(parse_expr_text("1 + 2"))[…]`: arguments may be any expression without local variables) |
| Method (`self` / `var self`) | 590 | **Not possible today**: `#test` on a method is a parse error ("expected a method ('fun ...') in impl block, found '#'") |

So 80 % needs `#test` on methods: the receiver as the first argument (`#test(C { n: 2 }, 3)[5]` above `fun add(self, k: int)`), and for `var self` methods the result only. That is a language change for the owner to decide.

The harvester: the Python interpreter runs the self-hosted compiler (`selfhost/gen_main.my`, the interpreter, the loader) over the examples and the error corpus with a hook on function entry and return. It records each call whose arguments and result print as Myla expressions under a size limit, keeps a few distinct cases per function (small ones first, every enum variant of the result where it can), and writes them as `#test` lines above the function. Generated cases record what the compiler does today (regression tests, not a specification), and a person reads them before they are committed. It needs the Python interpreter, so it runs before [[MYLA-219]] removes it; the self-hosted interpreter could carry the same hook later.

- [ ] The three places that state it agree with the decision
- [ ] The burn test: coverage per module and overall, a warning below 80 % (in the test output and as a CI annotation)
- [ ] `#test` on methods, if the owner decides for it (both parsers and checkers, both test runners)
- [ ] The harvester; cases generated, read and committed module by module, before [[MYLA-219]]
- [ ] The share past 80 %
