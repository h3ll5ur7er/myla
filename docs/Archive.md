# Archive

The documents written while Myla was designed and built, up to the self-hosting fixed point (June–July 2026). They are kept unchanged for their history and reasoning, but they are **not current**: they describe features as they were being designed. For how things are now, read [[Language]], [[Architecture]] and [[Project]].

[SUBPAGES]

## Contents

| Document | What it was | Superseded by |
| --- | --- | --- |
| [language-spec](Archive/language-spec.md) | The v0.0 language specification (variables, functions, structs, sized integers) | [[Language]] |
| [grammar](Archive/grammar.md) | The v0.0 EBNF grammar | [[Language/Grammar]] |
| [architecture](Archive/architecture.md) | The v0.0 design sketch of the Python toolchain | [[Architecture]] |
| [roadmap](Archive/roadmap.md) | Status, milestone history and the decision log as of 30 June 2026 | [[Project/Roadmap]], [[Project/Decisions]] |
| [known_issues](Archive/known_issues.md) | Gaps of the self-hosted compiler at v1.0 | [[Project/Known-issues]] |
| [self-hosting](Archive/self-hosting.md) | The plan for reaching self-hosting: gap analysis, tiers, milestone order, differential testing | [[Architecture/Self-hosted-compiler]] |
| [future-features](Archive/future-features.md) | The catalogue of post-v0.0 feature designs; almost all are implemented | [[Language]], [[Project/Roadmap]] |
| [clarification_needed](Archive/clarification_needed.md) | Open design questions during development, all resolved into the decision log | [[Project/Decisions]] |
| [v0.2-data-modeling](Archive/v0.2-data-modeling.md) | Design of enums, `match`, tuples, generics, `Option`/`Result` | [[Language/Structs-enums-and-match]] |
| [v0.3-collections-and-ops](Archive/v0.3-collections-and-ops.md) | Design of lists, maps, the string toolkit, bitwise operators, casts, `const` | [[Language/Collections-and-strings]] |
| [v0.4-abstraction](Archive/v0.4-abstraction.md) | Design of methods, closures, pipelines, traits | [[Language/Methods-and-traits]] |
| [v0.5-modules-and-runtime](Archive/v0.5-modules-and-runtime.md) | Design of modules, floats, `char`, the I/O runtime | [[Language/Modules]] |
| [subprocess_task](Archive/subprocess_task.md) | Notes on fork/pipe/poll/execve/wait4 in assembly, used to write `__run` | [[Architecture/Native-backend]] |

These files predate the wiki's naming convention (lowercase file names, no title heading), and some refer to paths that no longer exist.
