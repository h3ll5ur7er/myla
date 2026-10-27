---
id: MYLA-84
title: The lexers disagree on non-ASCII letters in identifiers
type: bug
status: backlog
priority: low
labels: [lexer, selfhost, spec]
---
The Python lexer accepts any Unicode letter in an identifier (`str.isalpha`/`isalnum` in [[src/myla/lexer.py#L90-L95]]); the self-hosted lexer accepts only ASCII letters ([[selfhost/util.my#L57-L63]]), and so do [[grammar/myla.ebnf]] and the tree-sitter grammar generated from it ([[MYLA-77]]). [[Language/Lexical-structure]] only says "a letter".

```myla
fun main() {
    let größe = 1
    print(größe)
}
```

`python3 myla.py run` prints `1`; `build/myla` fails with `lex error: unexpected character 'ö'` at 2:11.

ASCII-only is simpler (no Unicode tables in the self-hosted lexer, every tool agrees with the grammar as it is), so the likely fix is to make the Python lexer reject them too.

- [ ] Decide (ASCII only, or Unicode letters everywhere) and record it on [[Project/Decisions]]
- [ ] Make both lexers, the grammar file and [[Language/Lexical-structure]] agree
- [ ] A lexer gate case and an error-corpus file (or, for Unicode, a sample lexeme in `@sample IDENT`)
