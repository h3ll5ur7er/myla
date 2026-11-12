---
id: MYLA-565
title: "An invalid spec given to `x.format(spec)` on a builtin `T: Format` is reported at the call interpreted and in std.fmt natively"
type: bug
status: todo
priority: low
labels: [interpreter, native, diagnostics, parity]
---
Found by round 6's checker lane ([[MYLA-544]], C8). `x.format(spec)` on `x: T` with `T: Format` at a builtin `T` formats by a spec known only when it runs, so an invalid one is a runtime error. Both runners say `invalid format spec 'q'` and exit 1, but at different places: natively inside std.fmt, where `fmt_int` panics; interpreted at the call, as the interpreter formats with its own copy of std.fmt and only reaches the program's when the program loads std.fmt (with `import std.fmt as fmt` the interpreter's report is native code's). D183 wants the interpreter's report from both.

```myla
fun show<T: Format>(x: T, spec: str) -> str { return x.format(spec) }
fun main() {
    print(show(5, "q"))
}
```

```
$ myla run f1.my
runtime error: invalid format spec 'q'
  --> f1.my:1:62
$ myla build f1.my -o f1 && ./f1
runtime error: invalid format spec 'q'
  --> <myla>/std/fmt.my:209:28
```

The call is the better place (the spec is the caller's mistake, as a hole's invalid spec is a type error at the hole).

- [ ] One place on every runner, the call, as D183 asks: native code checks the spec at the call (`std.fmt.parse_spec`) before `fmt_int`, `fmt_float` or `fmt_text`, or the lowering passes the call's position
- [ ] A test in `tests/burn/test_compiler_parity.py`'s `RUNTIME_ERRORS`
