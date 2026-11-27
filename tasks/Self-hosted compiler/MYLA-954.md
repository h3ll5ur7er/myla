---
id: MYLA-954
title: "A variable named `format` breaks every f-string in its scope: `cannot call a value of type 'str'`"
type: bug
status: todo
priority: medium
labels: [checker, f-strings, diagnostics]
---
Found by [[MYLA-966]] and [[MYLA-965]]:

```myla fragment
fun f(format: str) -> str {
    return f"x {format}"
}
```

gives `type error: cannot call a value of type 'str'` at the f-string: its holes are lowered to calls of `format` by name, which the parameter (or a local) shadows. With an `int64` local named `format` the message is `cannot call a value of type int64`. Neither names the cause.

- [ ] A failing case first
- [ ] f-strings call the formatter by a name a program can't shadow (as `__fmt` or a resolved builtin), or the checker reports the shadowing at the variable with a hint
