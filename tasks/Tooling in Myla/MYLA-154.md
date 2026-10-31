---
id: MYLA-154
title: Generate the VS Code TextMate grammar from grammar/myla.ebnf
type: improvement
status: backlog
priority: low
labels: [editor, grammar]
---
Split from [[MYLA-77]], whose optional item it was: the tree-sitter grammar is generated from `grammar/myla.ebnf`, but the extension's TextMate grammar (`vscode-extension/myla/syntaxes/myla.tmLanguage.json`) is still written by hand ([[MYLA-54]] keeps it in step with the lexer's keywords).

- [ ] The keyword, type and operator lists of the TextMate grammar generated from the grammar description (`tools/grammar`)
- [ ] A test that the generated file is up to date
