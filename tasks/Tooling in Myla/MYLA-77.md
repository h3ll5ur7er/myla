---
id: MYLA-77
title: Grammar description and a tree-sitter grammar generated from it
type: feature
status: done
priority: medium
labels: [grammar, tree-sitter, editor, selfhost]
---
Part of the "everything in Myla" direction ([[Project/Roadmap]]). Supersedes [[MYLA-47]].

The compilers' parsers are hand-written ([[src/myla/parser.py]], [[selfhost/parser.my]]), so a tree-sitter grammar can't be derived from their code. Instead, one machine-readable grammar description is the single source for the editor grammar, and tests tie it to the compiler, so it can't drift the way the current hand-written `editor/tree-sitter-myla/grammar.js` did (it still follows the removed Rust dialect).

- [x] Turn the EBNF in [[Language/Grammar]] into a machine-readable file (in the repository, the wiki page generated from it or checked against it), including the newline/`;` separators (D61) and where line breaks are skipped
- [x] A generator written in Myla emits `grammar.js` and the highlight queries; tokens (keywords, operators, type names, literal forms) come from [[selfhost/tokens.my]] / [[selfhost/lexer.my]]
- [x] Newlines as a real token with explicit optional newlines in rules (no external C scanner); approximate where tree-sitter can't express the parser exactly (generic `<` vs less-than, struct literals in `if`/`while` headers, f-string holes)
- [x] Tests: tree-sitter parses every `.my` file of `examples/`, `selfhost/` and the stdlib without an ERROR node; programs generated from the grammar file are accepted by the self-hosted parser; the syntax-error corpus gives ERROR nodes where feasible
- [x] Optionally emit the VS Code TextMate grammar (moved to [[MYLA-154]]) from the same source (see [[MYLA-54]]): not done; the extension's TextMate grammar stays hand-written for now, and editors with tree-sitter support use the generated grammar

## How

Decision D63 on [[Project/Decisions]]; the design is on [[Architecture/Editor-tooling]].

- [[grammar/myla.ebnf]] is the syntax in an EBNF dialect with annotations for the generators: `@label` names the node an alternative makes, and directives declare the word token, extras, GLR conflicts, `@adjacent`/`@soft`/`@lexical` exceptions to the lexer checks, `@restrict` for the sampler and `@sample` lexemes. [[Language/Grammar]] shows the same rules without annotations; a burn test compares the two in canonical form.
- `tools/grammar` (Myla, about 1,800 lines with 42 `#test` cases) reads it (`ebnf.my`), checks it and writes `grammar.js` and `highlights.scm` (`treesitter.my`), and samples programs (`sample.my`). `scripts/gen_treesitter.sh` builds the tool and runs `tree-sitter generate --abi 14`. `selfhost/tokens.my` gained `keywords()`, so the keyword list has one source.
- Mapping: token rules become `token(/…/)`, choice and operator rules are hidden, operator levels (`R = H ( A @l | … )*`) become left-recursive with `prec.left(1)` so operators extend greedily like the parser, shared labels become aliased helpers (identical ones shared), and `X*` of one symbol shares a `_x_rep` helper. Newlines are a token; no external scanner.
- The generator rejects malformed grammars and ties every terminal to the self-hosted lexer: one token with the same text, words must be keywords, every keyword must be used.
- The sampler is guided by coverage over a whole run, with a cheapness bias growing with depth and size. It found two parser behaviours the grammar didn't state (no struct literal in a guard; no suffix after a lambda, which delta debugging of a tree-sitter failure narrowed down).
- `editor/tree-sitter-myla/` is regenerated; the fold, indent and injection queries are rewritten for the new node names. CI's burn job installs Node and the tree-sitter CLI.
- Follow-up: the Python lexer accepts non-ASCII letters in identifiers and the self-hosted lexer and the grammar don't ([[MYLA-84]]).

## Evidence

- The old hand-written grammar (still the Rust dialect) gave ERROR nodes on 45 of 63 corpus files; the generated one on none, and on none of 2,000 samples. All 19 lex and parse error files give ERROR nodes, and the queries compile.
- The self-hosted parser accepts all 50,000 samples of seeds 1 to 10 (5,000 each, about 1.7 s per seed).
- Mutation sweep: each of the 184 required terminals in syntactic rules made optional, one at a time, with 5,000 samples from one seed. 146 mutants produce a sample the parser rejects, 29 fail the grammar checks, and the 9 others don't change the language (for example `"[" ":"? "]"` only adds the empty list, which already exists). Before the coverage rule was strengthened, `f(a; b)` and `P { x 1 }` mutants went unnoticed.
- `tests/burn/test_grammar.py`: 10 tests, about 7 s; the keyword-list test fails when a keyword is dropped from `keywords()`; the tree-sitter ones were red with a stale cached parser of another `myla` grammar and green once the test builds its own.
- Full run: 466 unit, 4 integration and 401 burn tests pass; the bootstrap reaches its fixed point at 7,536,102 bytes (7,527,421 before; `keywords()` is new).
