---
id: MYLA-133
title: Hot spots of the self-compile
type: feature
status: done
priority: low
labels: [codegen, selfhost, runtime, performance]
---
The profile of the self-compile after [[MYLA-131]] (callgrind, instructions per function) showed runtime routines and front-end code at the top: `__list_grow` 5.2%, `__alloc` 4.2%, `__sb_append_bytes` 3.9%, `__map_hash` 3.2%, `__key_eq` 2.6%, `__str_eq` 2.4%, the parser's peeks 3.7%, `new_lexer` 1.4%. Each step is kept only if it pays.

- [x] `__str_eq` compares eight bytes at a time (and a string with itself at once): −1.8% instructions
- [x] `__map_hash` multiplies a value key (eight FNV-1a rounds before) and mixes a string in eight bytes at a time, the high half folded into the low one: −2.3%
- [x] The lexer keeps the list `chars` decodes (`[char]`, read `as int32`) instead of copying it into a `[int32]`, and appends an ASCII lexeme's bytes without building a string per character (`cp_utf8`): −4.7%
- [x] `==` on an enum without payloads whose `eq` is derived compares the tags inline (`tag_only_eq`, the enums found once by `find_tag_enums`) instead of calling the derived routine: −0.9% (a first version looked the enum up among all declarations for each `==`: −0.8%)
- [ ] ~~Copy list cells eight bytes at a time~~: −3.5% of callgrind's count, which counts `rep movsb` per byte, and no wall time; left out

## Evidence

- Compiling itself, 2,783,262,016 → 2,526,951,842 instructions (−9.2%), but only 1–2% less wall time (alternating 40 runs: best 0.838 → 0.831 s, median 0.907 → 0.889 s). With cache simulation the self-compile reads memory 927 million times and writes it 707 million times (65% of its instructions), mostly the generated code's frame cells, with few misses: its time is store-to-load latency in the generated code, which code quality ([[MYLA-121]]'s registers) moves and runtime routines barely do.
- `strings_and_keys_around_eight_bytes` (string equality at lengths 0–17 with a difference at each position, string keys of lengths 0–39, value keys of every magnitude, the tag compare) and `test_payload_free_enums_compare_tags` (no call for an enum without payloads, the routine for one with them) pass in every implementation.
- Unit 595, integration 2, burn 768 (5 skipped) and the extension's 54 tests pass; the bootstrap reaches its byte-identical fixed point (5,342,845 bytes).
