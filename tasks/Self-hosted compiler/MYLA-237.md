---
id: MYLA-237
title: "A receiver or argument is taken after a later argument that writes its variable"
type: bug
status: review
priority: medium
labels: [backend, parity, evaluation-order]
---
Found while fixing [[MYLA-238]]. [[Language/Expressions-and-operators]] says a method call evaluates the receiver first. With a read-only `self` and an argument that changes the receiver, both interpreters take the receiver first and both native backends after the arguments:

```myla
struct C {
    n: int,
}

impl C {
    fun bump_get(var self) -> int {
        self.n = self.n + 1
        return self.n
    }
    fun plus(self, k: int) -> int {
        return self.n * 100 + k
    }
}

fun main() {
    var c = C { n: 1 }
    print(c.plus(c.bump_get()))   // interpreters: 102, native: 202
}
```

- [x] Both backends copy a receiver or argument read from a variable that a later argument may write, when it is evaluated: `_aliased_args` in [[src/myla/compiler/codegen_x86.py]] (direct and indirect calls; `_may_write` now sees a method call in the code generator's form, `T.m(recv, args)`), `later_writes` and `stage` in `direct_call` and `indirect_call` of [[selfhost/lower.my]]
- [x] The Python interpreter likewise for function and closure calls (`_eval_args`); a method's arguments were copied already
- [x] A parity program in all four runners, its output pinned; [[Language/Expressions-and-operators]] says it

## Evidence

The fix found the bug wider than reported. On the program `argument_values_before_later_writes` of `tests/burn/test_compiler_parity.py` (a receiver, a function's argument, a list element's receiver, an aggregate argument after the receiver, a closure's argument, a binary operator), before:

| Runner | Output |
| --- | --- |
| Python interpreter | 102, **202**, 102, 10506, **202**, 102 |
| Self-hosted interpreter | 102, 102, 102, 10506, 102, 102 |
| Both native backends | **202, 202, 202, 10606, 202**, 102 |

After: all four print 102, 102, 102, 10506, 102, 102 (pinned by `TestArgumentOrder` in `tests/unit/test_interpreter.py`; the parity test compares the native binary with the interpreter). The self-hosted compiler grows by 16 KB (6,194,029 to 6,210,821 bytes: its own source has such calls, now copying); a self-compile takes the same time (1.03–1.10 s before, 1.01–1.05 s after, three runs each).

Unit 627, integration 2, burn 836 (5 skipped) and the extension's 54 tests pass on commit 2f49187; the bootstrap reaches its byte-identical fixed point (6,210,821 bytes).
