---
id: MYLA-293
title: "Defaults in messages: `become`'s word count and `#test`'s arity"
type: improvement
status: done
priority: low
labels: [diagnostics, defaults]
---
Found by the review of 6 November 2026 ([[Project/Review-2026-11]]). Two messages don't mention the defaults the caller filled in: a 6-argument `become g(…)` to a function with two defaults says "passes 8 argument words, 2 of them on the stack"; a `#test` case that leaves a default out says "'#test' expects 2 argument(s), got 1" (a case gives every argument, as documented, but the message doesn't say so).

- [x] Both messages name the defaults; a burn test for each

## Evidence

- `'#test' expects 2 argument(s), got 1: a case gives every argument, the defaults of 'b' too` when the arguments left out all have defaults (`defaulted_from` in [[selfhost/checker.my]]).
- `'become' passes 8 argument words, 2 of them on the stack, but 'h' received 0 there, counting the defaults of 'x' and 'y' the call leaves out` (`BecomeWords.defaults`).
- `test_errors` in `tests/burn/test_default_params.py` (the cases `test_case` and `become_words`); `tests/burn/test_register_args.py`'s message without defaults is unchanged. Both modules pass.
