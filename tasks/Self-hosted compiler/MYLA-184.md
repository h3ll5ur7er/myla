---
id: MYLA-184
title: "The #test convention in selfhost/: 1,164 of 1,259 value-returning functions have none"
type: chore
status: review
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
- [x] The burn test: coverage per module and overall, a warning below 80 % (in the test output and as a CI annotation): `tests/burn/test_selfhost_coverage.py`, `scripts/test_coverage.py`
- [x] `#test` on methods (D116, [[MYLA-236]])
- [x] The harvester (`scripts/harvest_tests.py`); a first round of cases generated, validated by both runners and committed
- [x] The share past 80 %
- [x] Receivers for the methods on the compiler's state objects: receiver factories and AST factories (the owner's choice, with more workloads)

## Evidence

- First round (2026-11-01): the harvester ran the self-hosted CLI in the Python interpreter over 342 workloads (`check`, `build`, `test`, `run` of the 32 examples, `check` of the error corpus) in about 40 minutes on 4 cores, recorded calls of 335 functions and wrote 852 cases (at most three per function, spread over the recorded sizes, each at most 220 characters of arguments and result). Both runners pass every case; validation removed none.
- Coverage of value-returning functions in `selfhost/`: 97 of 1,274 (8 %) before, 432 of 1,274 (34 %) after.
- What stops it at a third: 540 of the functions without cases are methods on the compiler's state objects (`Checker` 150, `CodeGen` 106, `Parser` 98, `Interp` 93, `Lower` 74, `Norm` 19), whose receiver is the whole state and can't be written as a literal; and most of the 259 free functions without cases are on paths the examples don't reach (the REPL, the project commands, `fetch`, rare diagnostics) or take compiler state. Raising the size limit adds almost nothing (5 functions under 400 characters on a probe).
- Second and third rounds (2026-11-01, after the owner chose receiver factories and more workloads): factories build the compiler's state from a one-line snippet (`parser_on`, `checker_on` without the prelude, `interp_on`, `codegen_on`, `lower_on` with an entry block) and AST values from snippets (`expr_of`, `stmt_of`, `type_expr_of`, `block_of`, `pattern_of`, `fun_of`); `generate` runs every function without cases in the Python interpreter, factory parameters from snippet sets, other parameters from recorded values or pools by type, and stops a call before any I/O primitive runs. New workloads: five REPL sessions, a project with a path dependency (`build`, `run`, `test`, `check`), `clean`, `new`, `fetch` from a local Git repository, `build -g`. Three small functions got hand-written cases.
- Coverage of value-returning functions in `selfhost/`: 8 % → 34 % → 61 % → 70 % → **80.2 %** (1,030 of 1,285); `#test` lines in `selfhost/` 297 → 1,898, 524 of them with a factory. One case per function that needs factory state, as each costs a factory call in each runner: the burn suite went from 383 s to about 430 s.
- Validation found a bug: the self-hosted interpreter dropped an argument's change to a `var self` receiver ([[MYLA-238]], fixed), and with it a difference in the read-only receiver's order between the interpreters and native code ([[MYLA-237]]).
- A first version of `generate` let a function that makes directories run with pooled names: seven `myla new` skeletons appeared in the checkout (removed; no tracked file was touched). Generated calls now stop before any I/O primitive runs and work in `build/harvest/sandbox`.
- Gates: unit 626, integration 2, burn 835 (5 skipped) and the extension's 54 tests pass on commit b4100ff, the last of the third round; the bootstrap reaches its byte-identical fixed point (6,194,029 bytes).
