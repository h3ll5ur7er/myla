---
id: MYLA-12
title: "Interpreter crashes on strings that aren't valid UTF-8"
type: bug
status: backlog
priority: medium
labels: [interpreter, strings, parity]
---
`__read_file` decodes with `errors="surrogateescape"` ([[src/myla/interpreter.py#L784-L795]]), but `len`, `s[i]` and `__write` encode with plain `"utf-8"`, which rejects surrogates.

## Steps to reproduce

```bash
printf 'ab\xff\xfecd' > bin.dat
```
```myla
from std.fs import read_to_string
fun main() {
    match read_to_string("bin.dat") {
        Ok(s) => print(len(s))
        Err(e) => print("err")
    }
}
```

## Actual

The native binary prints `6`; the interpreter dies with `UnicodeEncodeError: … surrogates not allowed` ([[src/myla/interpreter.py#L820-L828]]).

## Done when

- [ ] One helper encodes interpreter strings to bytes with `surrogateescape`, used by `len`, indexing, `print`, `__write`, `format`, `append`, `+` and map hashing
- [ ] `chars()` on invalid UTF-8 behaves the same in both backends (the native decoder can read past the end on a truncated sequence: [[MYLA-17]])
- [ ] Parity test with a binary file
