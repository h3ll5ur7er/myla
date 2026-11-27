---
id: MYLA-583
title: Myla owns its keyword list, not the retired Python lexer
type: improvement
status: backlog
priority: medium
labels: [grammar, tests]
---
The keyword list is still pinned to the Python lexer that D101 retired. `test_grammar.test_the_keyword_list_is_the_lexer_s` compares `keywords()` in [[selfhost/tokens.my]] with `_python_keywords()`, an oracle the frozen recordings answer (`@golden("grammar.keywords")`, [[tests/burn/_golden.py]], [[MYLA-219]]). Those recordings can't be changed any more, so the language can't gain a hard keyword: every new word has to be soft, an identifier the parser recognises in place, as `defer` is (`@soft` in [[grammar/myla.ebnf]]). Found by [[MYLA-581]] and listed in [[MYLA-582]].

The reference should be Myla's own: one place in the repository that the lexer, the grammar description, the generated tree-sitter grammar and the hand-written lists all follow, and that a feature task changes on purpose. A good shape is the EBNF's keyword set and `tokens.keywords()` checked against each other in both directions, with `keyword_kind` and `keywords_agree` (already in `tokens.my`) keeping the lexer in step.

- [ ] Decide the source of truth (proposal: `grammar/myla.ebnf`'s keywords, with `tokens.keywords()` derived or checked against it) and record it as a decision in [[Project/Decisions]]
- [ ] Replace `test_the_keyword_list_is_the_lexer_s` and `_python_keywords` with a check against that source, with no recorded Python answer involved
- [ ] The same check covers the hand-written lists that drift today: `tools/lsp/features.my` `completion_keywords()` and the VS Code TextMate grammar (see [[MYLA-154]], which would generate the latter)
- [ ] Written down how a hard keyword is added: the files to change, and what it costs programs that use the word as a name (`tests/burn/test_grammar.py` docstring, [[.claude/skills/myla/reference/compiler.md|the skill's compiler reference]] "Syntax", [[Language/Lexical-structure]])
- [ ] Shown to work: a scratch branch adds a hard keyword end to end, and every gate passes or fails for the right reason
- [ ] The other `@golden` oracles surveyed (27 in 17 burn-test modules: lexer tokens, parser trees, checker verdicts, interpreter and native runs, CLI and LSP answers): for each, whether a test of the code's own (an expectation file, a `#test`) should replace the frozen answer, split into tasks of their own where it should
