---
id: MYLA-135
title: Concurrency in the language and both checkers
type: feature
status: todo
priority: medium
labels: [concurrency, language, checker, selfhost]
---
D89, first step of [[MYLA-61]]: the syntax and the rules, on the Language pages and in both checkers (with the same errors).

- [ ] The syntax by example on a new Language page, for review: `actor` declarations and methods, `async fun`, `await`, `async let`, task groups, `#main async fun main()`; keywords and grammar
- [ ] Lexers and parsers (Python and self-hosted)
- [ ] The rules: where `await` may stand, calling async functions only from async code, actor isolation (state only through `self` in its own methods, every outside call awaited), sendability at every crossing, `async let` and groups not outliving their scope
- [ ] The error corpus for each rule
