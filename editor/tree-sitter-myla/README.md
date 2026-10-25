# tree-sitter-myla

A [tree-sitter](https://tree-sitter.github.io/) grammar for **Myla**, for editor
syntax highlighting and structural navigation.

> This grammar is **editor tooling only** and is intentionally kept off the
> compiler path. The authoritative parser is the Python toolchain's
> (`src/myla/parser.py`, grammar in `docs/Language/Grammar.md`), which resolves
> ambiguities (struct literal vs block) that a context-free grammar cannot.
> Expect this grammar to be looser than the real parser. It was written for
> the experimental Rust edition's dialect (semicolons, `select`, actors), removed
> in MYLA-70, and still follows it in places (MYLA-47).

## Usage

```bash
npm install
npm run generate   # tree-sitter generate
npm test           # if you add corpus tests under test/
```

Point your editor's tree-sitter integration at the generated parser to get
highlighting for `*.my` files.
