# Editor tooling

[TOC]

## Language server

`src/myla/lsp/` is a language server built on pygls 2 over stdio. It is an optional extra, so the rest of the toolchain stays dependency-free.

```bash
uv sync --extra lsp
python3 myla.py lsp            # or: python -m myla.lsp
```

| Module | Role |
| --- | --- |
| `server.py` | pygls server, document store, debounced diagnostics, feature handlers |
| `compiler_adapter.py` | Runs `loader.link` + `types.check` on a buffer and turns a `MylaError` into a diagnostic |
| `positions.py` | 1-based code-point positions ↔ 0-based UTF-16 LSP positions; squiggle width |
| `symbols.py` | Builds a symbol tree from the parsed buffer; outline; picks the best declaration |
| `lookup.py` | The identifier under the cursor and every occurrence, from the token stream |
| `definition.py`, `hover.py`, `references.py`, `completion.py` | The features |
| `workspace.py` | Scans the workspace's `.my` files (mtime-cached symbols) |

**Diagnostics** use the real compiler: the open buffer is passed to the loader as a source override, so unsaved text is checked. The compiler stops at the first error, so there is at most one diagnostic. Opening and saving check immediately; edits are debounced by 0.4 s.

**Everything else is name-based**: the buffer is only lexed and parsed (not checked), and definitions, hover, references and completion match identifiers by name in the file and across the workspace. Imports and scopes are ignored, locals don't resolve, and member completion offers every known member.

Supported: `didOpen`/`didChange`/`didSave`/`didClose`, `documentSymbol`, `definition`, `hover`, `references`, `completion`. Not supported: formatting, rename, semantic tokens, signature help, code actions, workspace symbols.

A declaration's selection range (the target of go-to-definition, and the token `includeDeclaration: false` drops from references) is its name token, found in the token stream from the declaration's keyword (MYLA-48); for an `impl` it is the target type. Positions sent by the editor are UTF-16 offsets, which `positions.from_lsp_character` converts before a line is sliced.

An error in an imported module is published for that module's URI (it shows in the Problems panel and in that file), and cleared there once a later check of the importing document no longer finds it (MYLA-10); other open buffers are checked with their unsaved text. `tests/integration/test_lsp_diagnostics.py` drives the real server over stdio when pygls is installed; `tests/unit/test_lsp_features.py` covers positions, symbols, definition, references and completion without it (MYLA-52).

The Python server is to be replaced by one written in Myla ([[MYLA-80]]), which takes the open findings of [[MYLA-49]], [[MYLA-50]] and [[MYLA-51]] as requirements.

## VS Code extension

`vscode-extension/myla/` contributes the `myla` language for `.my` files: a TextMate grammar, snippets, a language configuration and a language client.

- The client looks for `myla.py` (setting `myla.compilerPath`, then the workspace folders) and for Python (`myla.pythonPath`, then `<repo>/.venv`, then `python`), and starts `python myla.py lsp` with the repository as working directory. `${workspaceFolder}`, `${userHome}` and `~` are expanded in the two path settings. Changing a setting restarts the server.
- Settings: `myla.compilerPath`, `myla.pythonPath`, `myla.diagnostics.enable` (hides diagnostics through a client middleware; the server keeps running), `myla.trace.server` (the client id is `myla`).
- `npm run package` builds the `.vsix`; it isn't committed. `.vscodeignore` keeps sources out of it.
- `tests/unit/test_vscode_extension.py` checks the grammar against the lexer's keywords and the built-in type names, and parses every snippet ([[MYLA-54]]).

## tree-sitter grammar

`editor/tree-sitter-myla/` is a tree-sitter grammar (with bindings for C, Go, Node, Python, Rust and Swift, and highlight, fold, indent and injection queries), **generated** from [[grammar/myla.ebnf]] since [[MYLA-77]].

### The grammar description

[[grammar/myla.ebnf]] is the machine-readable syntax of Myla: the EBNF of [[Language/Grammar]] plus annotations for the generators (its header documents them). `tests/burn/test_grammar.py` compares the wiki page and the file in the canonical form `grammar canon` prints (annotations dropped, spacing and redundant groups normalised), so a change goes into both.

Rules in capitals whose bodies use only terminals, classes and lowercase helpers are tokens (`IDENT`, `INT`, `NL` …); other capitalised rules (`SEP`, `ARM_SEP`) are syntactic but make no node. Newlines are a token (`NL`) and every place that allows a line break says so, as the parser does; that is what lets the editor grammar work without an external scanner.

### The generator

The grammar tool [[tools/grammar/main.my]] is written in Myla and built natively (`scripts/gen_treesitter.sh` builds it, writes `grammar.js` and `queries/highlights.scm`, and runs `tree-sitter generate --abi 14` for `src/`):

| Module | Role |
| --- | --- |
| `ebnf.my` | Reads the grammar file (and the ```ebnf blocks of a Markdown page) into rules and directives; the canonical form |
| `treesitter.my` | `grammar.js` and `highlights.scm`; the checks below |
| `sample.my` | Random programs from the grammar |
| `highlights.scm` | The hand-written, structural part of the highlight query |

How the description becomes tree-sitter:

- A token rule becomes `token(/regex/)` with its fragments inlined; `@immediate` (f-string text) makes it `token.immediate` with a lexical precedence over the extras.
- A syntactic rule keeps its name. It makes no node (`_name`) when it only chooses between other symbols and labelled alternatives (`statement`, `primary`, `type`), when it has the operator form below, or when its name is in capitals. Single-symbol rules (`expression = pipe`) are inlined.
- A labelled alternative (`… @struct_literal`) becomes a rule of that name. When several make the same node (`binary_expression`, `match_arm`), each is a hidden helper aliased to the name; identical alternatives (`"self" @self` in `place` and `primary`) share one, or the parser couldn't tell which of two equal rules to reduce.
- `R = H ( A @l | … )*` (the operator levels, `postfix`, `pattern`, `place`) becomes left-recursive: each suffix wraps what precedes it in a node `l`, so trees nest like the parser's AST. Each suffix has `prec.left(1)`, which makes an operator extend the expression before it rather than end an enclosing construct, such as a lambda's expression body: the recursive-descent parser is greedy there.
- `X*` and `X+` of a single rule share a helper `_x_rep`, so every repetition of `NL` or `SEP` shifts the same symbol; without it, `"," NL* x` next to `"," NL* "}"` was a conflict.
- `@word`, `@extras` and `@conflict` become `word`, `extras` and `conflicts`. The declared conflicts are the places where the parser uses context or scans ahead: a lambda's `( … )`, a struct literal in a condition, an assignment target, tuple versus function types, `as T <`, and a newline before `else`.

Highlights: the hand-written structural part (`tools/grammar/highlights.scm`), then generated lists of the grammar's keywords, operators and punctuation. Left to the hand-written part, so that no two patterns capture the same node: a terminal it captures itself (`"self" @…`), the terminals of a rule whose node it captures (`(prim_type)`), and a labelled terminal whose node it names (`(boolean)`).

### Checks

Before generating, the tool rejects duplicate, undefined, unused and empty-matching rules, and ties every terminal to the compiler: each must lex, with the self-hosted lexer, as one token with the same text, a word must be a keyword (`keywords()` in [[selfhost/tokens.my]]), and every keyword must occur in the grammar. The exceptions are declared: `@adjacent` (`<<`, `>>`, two touching tokens, D44), `@soft` (`_`, an identifier the parser treats specially) and `@lexical` (`fstring`, lowered by the lexer).

### Sampling

`grammar sample <grammar> <seed> <n> [parse]` prints random derivations, or checks that the self-hosted parser accepts them. `@sample` gives the tokens' lexemes, and `@restrict R X` keeps X out of R's subtree where the parser's context would read the text differently (struct literals and lambdas in conditions, parentheses in guards, named types in casts, line breaks in f-strings).

Choices are guided by coverage, counted over the whole run: an alternative or optional part produced less than a quarter as often as the others is taken while the program is small; otherwise a choice becomes cheap (fewest tokens) with growing depth and size. A few long runs therefore test more than many short ones. The burn test parses 10,000 samples with the self-hosted parser and 2,000 with tree-sitter. A mutation sweep (each required terminal made optional, one at a time) measured what that catches: of 184 mutants, 146 produce a sample the parser rejects, 29 fail the checks, and the other 9 don't change the language. Sampling also found two parser behaviours the grammar now states: struct literals are off in guards, and a lambda takes no suffix ([[Language/Grammar]]).

### Differences from the parser

The editor grammar accepts a little more than the compiler: keywords are contextual (`let if = 1` parses), a struct literal in a condition parses, and so does `_` as an ordinary expression next to a hole. Every syntax error of the error corpus still gives an ERROR or MISSING node. The grammar is a little stricter than the parser in one place: a suffix after a lambda whose body can't take it (`(x) => x as T [0]`) is rejected; no code in the repository does that.
