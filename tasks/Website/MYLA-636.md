---
id: MYLA-636
title: "The academy after the first review: three bugs and a wider multiverse"
type: feature
status: done
priority: high
labels: [website, learn]
---
The owner's review of the live site (MYLA-634): the next exercise kept the last one's code; a test exercise was solved by deleting its `#test` cases and writing a trivial one; some second hints all but gave the answer. And the references should reach beyond the shows named in the brief: Harry Potter, The Witcher, Watch Dogs, GTA, Minecraft, Star Wars, Star Trek, Stargate, DC, Disney and more.

- [x] The editor takes a new program when its input changes (the next exercise opens with its own starter); an e2e test
- [x] Check runs the exercise's own cases and new hidden ones, not the learner's (`core/exercise-check.ts`, the same in `check-course.mjs` and `test_website.py`); `own-tests` for the exercise about writing tests; an e2e and a burn test of the cheat
- [x] Hints rewritten: the second points at the construct or method, never the line
- [x] Chapter 9, The Multiverse (strings, sorting, format specs): The Witcher, Harry Potter, Stargate, Watch Dogs, Batman, Minecraft, GTA
- [x] 20 levels and 28 achievements from more franchises; more loading, 404, footer, solved, failed and time-out lines
- [x] The hero says what sets Myla apart, not that it compiles itself (every self-hosted language does): "A smart language with no hidden machinery", no implicit conversions, no garbage collector, no libc, one toolchain for three targets; the feature cards: values, race-free concurrency, the standard library, examples as tests, the checker, written in Myla. The page title, meta description and footer match

## Evidence

- Bug 1: `e2e` "the next exercise opens with its own code" failed before the fix (the editor still held `print("Hello, Galaxy!")`) and passes after it.
- Bug 2: `exercise-check.spec.ts` (8 specs); `test_website.py`'s cheat test (`#test(0)[0]` over `return 0` for `triangle`) and the e2e "replacing the given cases with a trivial one doesn't pass". 33 exercises have `// hidden:` cases; every exercise still fails as given and passes solved: `npm run check-course` "55 exercises in play.wasm, 0 wrong", `python3 -m unittest tests.burn.test_website` 5 tests OK.
- 9 chapters, 55 exercises, 1,875 XP; the top level needs 1,560 (83 %).
- The hero chosen by the owner from mock-ups in light, dark and phone widths: three lines at 1360 px, the facts above the fold, no sideways scrolling on a phone.
- `npm test`: 14 node tests and 35 Vitest specs pass; `ng build` clean; Playwright 26 passed.

Signed off by [[Project/Review-2026-11-17]] (done).
