---
id: MYLA-233
title: "A burn test for the code blocks in the docs"
type: improvement
status: review
priority: medium
labels: [docs, tests]
---
D114 ([[MYLA-213]]): every fenced `myla` block in `docs/` and the README is extracted and checked; a block with a `main` runs, and its printed lines are compared with the `// output` comments. Blocks that are deliberately fragments or deliberately wrong carry a marker (`myla fragment`, `myla error`).

- [x] The extractor and the burn test, running on the self-hosted toolchain
- [x] The blocks that fail today fixed or marked; the convention in [[Development/Conventions]]

## Evidence

- `tests/burn/test_doc_blocks.py` extracts the 50 `myla` blocks of `docs/` and the README (fences inside lists included). Each must check with `build/myla check`. A block with a `main` (37 of them) must also run with exit 0, in the interpreter and as a native binary alike, in an empty directory with empty stdin, and print exactly its `// output:` section if it has one.
- **The convention:** an output section at the end of the block, `// output:` and then one `// ` line per printed line. I chose it over reading the inline comments, which mix values (`// 21`) and prose (`// a fun as a value`). It is on [[Development/Conventions]] and in the myla skill.
- **Before:** 44 blocks checked and 6 failed.
  - Five were pieces of programs: the signature listing on [[Architecture/Project-tool]], three Concurrency blocks using `fetch`, `Pool` and `Auditor`, and the statements about `?` in lambdas. Now marked `myla fragment`.
  - One was the list of rejected code under "Errors" on [[Language/Concurrency]]. Now marked `myla error`.
- **Output sections:** 36 runnable blocks got one, written from their runs and compared with the text's own claims (`// 21`, `// 2000`, `total area 19` and the others agree). One block prints nothing (it reads stdin) and has none.
- **Test-first:** the test failed on the six blocks before they were marked and passes after: 3 tests, about 3 s.

