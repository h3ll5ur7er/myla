---
id: MYLA-718
title: "gen_main ignores a failed write of its output: a full disk gives an empty .s and status 0"
type: bug
status: todo
priority: medium
labels: [toolchain, bootstrap]
---
Found while building [[MYLA-703]], on a machine whose disk filled up: `build/stage3 file.my lib > out.s` wrote nothing and exited with 0, so a comparison of two such outputs said "same" (two empty files), and a bootstrap's stages would compare two empty assemblies.

`selfhost/gen_main.my` writes the assembly with `write(1, asm)` (std.io's, a `Result<(), IoError>`) and drops the result; a Myla program's own `print` reports the same failure (`runtime error: write failed: no space left on device`, status 1).

Reproduction (2026-11-15, MYLA-703's branch):

```
build/stage3 examples/hello.my lib > /dev/full; echo $?     # 0, nothing said
printf 'fun main() {\n    print("hello")\n}\n' > p.my
build/myla build p.my -o p && ./p > /dev/full; echo $?        # runtime error: write failed: no space left on device, 1
```

- [ ] gen_main (and the other tools' `write(1, …)` of their report: `selfhost/driver.my`'s test report, `selfhost/interp.my`'s) says why and exits with 1 when the write fails
- [ ] A test: the tool's output to `/dev/full`
- [ ] Whether a dropped `Result` should be a warning (D-row to propose): `write(1, asm)` compiles silently
