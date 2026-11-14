# The course

The exercises of the website's learn area ([MYLA-634](../tasks/Website/MYLA-634.md), D208), rustlings-style: each is a Myla program that doesn't work yet, and the tests or the output that show when it does. The site shows them at `/learn`; [docs/Architecture/Website.md](../docs/Architecture/Website.md) describes how.

## A chapter

`<NN>-<id>/chapter.md`: a header of `key: value` lines, a blank line, then the chapter's introduction in Markdown (wiki links work):

```
title: Don't Panic
emoji: 🌌
tagline: Printing, values and your first functions. Bring a towel.

Welcome aboard. …
```

Chapters open in order: one opens when 60 % of the one before is solved. Each has exactly one boss, its last exercise.

## An exercise

`<NN>-<id>.my`, and its solution `<NN>-<id>.solution.my`. The exercise starts with a header of `//` lines:

```myla fragment
// title: The Answer
// xp: 10
// expect: The answer is 42
// hint: `6 + 7` is 13. Deep Thought used a different operator.
// hint: Multiplication is `*`.
//
// The instructions, in Markdown, up to the first line that isn't a comment.
fun main() {
    let answer = 6 + 7
    print(f"The answer is {answer}")
}
```

- `title`, `xp` (positive) and at least one `hint` are required; `boss: true` marks the chapter's boss.
- With `expect` lines (one per line of output), the exercise is solved when running it prints exactly them. Without, it is solved when all its `#test` cases pass, at least one.
- The code below the header is what the learner starts from: it must not be solved (it doesn't compile, fails a test, prints something else, or runs for more than 10 seconds). The solution must be.

## Checking

```bash
python3 -m unittest tests.burn.test_website      # with build/myla's toolchain
cd website && npm run check-course              # through play.wasm, as the browser runs them
```

Both run in CI. The references are part of the fun: keep them light, and keep the instructions exact.
