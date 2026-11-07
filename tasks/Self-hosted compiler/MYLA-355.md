---
id: MYLA-355
title: "Native: assert with a computed message fails the IR verifier"
type: bug
status: review
priority: high
labels: [codegen, lowering, ownership]
---
Found by the `std.str` lane ([[MYLA-321]]). Natively, `assert(cond, msg)` stops the compiler when `msg` is computed inline, such as an f-string or a concatenation: "internal error: main: IR verifier: L2: drop of $1 (__temp), which holds no value". The interpreter runs the same program. A message held in a variable works, and so does `panic(f"…")`.

```myla fragment
fun main() {
    let t = "a"
    assert(t != "b", f"'{t}'")
}
```

## Cause

`intrinsic` in [[selfhost/lower.my]] computes the message only in the failing branch, which is right: a message isn't evaluated when the assertion holds. But the message's owned temporaries were registered with the enclosing statement. The statement's end then dropped them on the passing path too, where they hold no value.

- [x] The message's temporaries are the failing branch's own: a temporary scope opened there and closed without drops, since the branch ends the program
- [x] `test_compiler_parity`'s `test_assert_with_a_computed_message`: an f-string and a concatenation, passing and failing

## Done (2026-11-07)

- `intrinsic` opens a temporary scope for the message in the failing branch and closes it without drops before the `Panic` terminator. The interpreter needed nothing.
- Test first: `test_assert_with_a_computed_message` (an f-string and a concatenation, each once passing and once failing) failed to build before (the verifier's error) and passes after. The other `assert` tests still pass.
- `scripts/bootstrap.sh`: byte-identical fixed point (9,859,129 bytes).
