---
id: MYLA-775
title: "A function named with a letter outside ASCII doesn't assemble with clang (Windows, aarch64 from x86-64, wasm32)"
type: bug
status: todo
priority: medium
labels: [backend, platforms, windows]
---
Found by [[MYLA-757]] (2026-11-16, at 478d656): identifiers may use letters of any script (D72), and the code generator writes a function's symbol as `myla_<name>` byte for byte. GNU `as` takes UTF-8 in a symbol, clang's assembler doesn't, so every target that clang assembles fails on such a function once it isn't inlined: x86_64-windows, aarch64-linux built on x86-64 (and x86_64-linux built on aarch64), wasm32-wasi. With `-g`, which inlines nothing, `examples/unicode.my` fails on Windows (its `fläche`); without it, a recursive one does:

```myla
fun größe(n: int) -> int {
    if n <= 0 { return 0 }
    return n + größe(n - 1)
}

fun main() {
    print(größe(10))
}
```

```
$ build/myla build uni.my --target x86_64-windows -o uni.exe
myla: assembler failed
uni.exe.s:3521:14: error: unexpected token in argument list
        call myla_größe
$ build/myla build uni.my --target wasm32-wasi -o uni.wasm
uni.wasm.s:131:19: error: Expected (, instead got: �
        .functype myla_größe (i64) -> (i64)
$ build/myla build uni.my --target aarch64-linux -o uni.a64
uni.a64.s:7164:12: error: unexpected token in argument list
        bl myla_größe
```

- [ ] A symbol clang's assembler takes for every name: quoted (`"myla_größe"`, which clang and GNU `as` both read, if wasm's directives take it too) or the bytes outside ASCII escaped in the name (`myla_gr$c3$b6$c3$9fe`, the name gdb and the backtraces show then); x86-64 Linux's own output stays as it is if the quoting is only where it is needed, or the choice says why not
- [ ] A test that builds such a function (called recursively, so it isn't inlined) for every target and runs it, and `-g` on Windows on `examples/unicode.my`
