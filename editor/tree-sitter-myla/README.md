# tree-sitter-myla

A [tree-sitter](https://tree-sitter.github.io/) grammar for **Myla**, for editor
syntax highlighting, folding, indentation and structural navigation.

`grammar.js` and `queries/highlights.scm` are **generated**: the source is the
machine-readable grammar [`grammar/myla.ebnf`](../../grammar/myla.ebnf) (the same
rules as the wiki page `docs/Language/Grammar.md`), turned into tree-sitter by
the grammar tool in [`tools/grammar`](../../tools/grammar), which is written in
Myla. Don't edit them by hand; change the EBNF (and for highlights the
hand-written part, `tools/grammar/highlights.scm`) and regenerate. `src/` is
what `tree-sitter generate` makes of `grammar.js`. The other queries (`folds`,
`indents`, `injections`) are hand-written.

Newlines are real tokens, as in the compiler, so the grammar needs no external
scanner. Where the compiler's parser decides with context (struct literals are
off in `if`/`while`/`match` heads) or by scanning ahead (a lambda is a `( … )`
followed by `=>`), the grammar declares a conflict and tree-sitter keeps both
readings until one fails.

## Regenerating

```bash
cd editor/tree-sitter-myla && npm install   # the tree-sitter CLI, once
cd ../.. && scripts/gen_treesitter.sh       # grammar.js, highlights.scm, src/
```

## Tests

`tests/burn/test_grammar.py` (run with the burn suite, or `npm test` here)
checks that the generated files are current, that tree-sitter parses every
Myla file of the repository without an error node, that every syntax error of
the error corpus gives one, that the self-hosted parser accepts thousands of
programs sampled from the grammar, and that the queries compile.
