---
id: MYLA-223
title: "Compound assignment"
type: feature
status: todo
priority: medium
labels: [language, ergonomics]
---
D104 (2) ([[MYLA-215]]): `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`, `<<=`, `>>=` mean `x = x op y`, with the place (`a[i()].f`) evaluated once; operator overloading applies through the operator's trait.

- [ ] Lexer, parser, grammar; checker (the target must be a `var` place, the operator defined for its type); lowering with the place's indices computed once
- [ ] A test that an index expression with a side effect runs once; error-corpus files
- [ ] [[Language/Statements]] ("There is no compound assignment yet" goes), the skill and `AGENTS.md` ("no `+=`")

Order: after [[MYLA-219]] this touches only the self-hosted toolchain (checker, interpreter, lowering) and the grammar; done before it, the Python checker and interpreter need it too. Using it in `selfhost/` itself needs a seed that knows it ([[MYLA-218]]).
