---
id: MYLA-54
title: VS Code grammar and snippets describe a different Myla
type: bug
status: backlog
priority: low
labels: [vscode]
---
The TextMate grammar and snippets mix in the Rust dialect and miss parts of the real language:

- [ ] The grammar highlights `actor`, `async fun`, `spawn`, `go`, `await`, `chan`, which the Python/self-hosted Myla doesn't have
- [ ] The type pattern lists `f32`, `f64`, `void` but not `float32`/`float64` (`\bfloat\b` doesn't match `float32`)
- [ ] The Trait snippet has a method body (traits hold signatures only)
- [ ] The Impl snippets omit the `self` receiver, which is a parse error (`examples/errors/parse_method_no_self.my`)
- [ ] The Actor and Async snippets are for constructs that don't exist
- [ ] The `#test` snippet lacks the `(args)[expected]` the checker requires
