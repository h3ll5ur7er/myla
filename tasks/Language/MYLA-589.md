---
id: MYLA-589
title: A line that starts with .method continues the expression
type: feature
status: backlog
priority: medium
labels: [language, parser]
---
Chained calls can't be broken across lines the usual way: a line starting with `.map(f)` is a parse error, because a newline ends the statement unless the line ends with a binary operator or a bracket is open (D104). Wrapping the whole chain in parentheses works today and is the workaround:

```myla fragment
let ys = (xs
    .map((x: int) => x * 10)
    .filter((x: int) => x > 10))
```

Most languages with newline-terminated statements continue a line that starts with `.` (Swift, Kotlin). In Myla it collides with one thing: a match arm's pattern may start with `.` (`.Red => 1` on its own line). The parser can tell them apart: in a match arm list a new line starting with `.Name` is a pattern when the tokens up to `=>` form one; elsewhere (and after an arm's expression when no `=>` follows on that line) it continues the expression.

- [ ] Choose: leading-dot continuation with the match-arm rule above, or drop Swift-style `.V` patterns (a breaking change), or keep parentheses as the only way; record the decision (with D104)
- [ ] Tests first: chains across lines in statements, arguments, `return`, lambdas' bodies; match arms with `.V` patterns after a chain; the error corpus for what stays an error
- [ ] Lexer/parser (`emit_newline`/`continues_line` in [[selfhost/lexer.my]], or the parser's postfix loop), the EBNF and the tree-sitter grammar
- [ ] Docs: [[Language/Lexical-structure]], [[Language/Statements]], the skill (habits table, `reference/syntax.md`)
