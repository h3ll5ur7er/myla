---
id: MYLA-213
title: "Decision: the tutorial and documentation plan, where it lives and how it is checked"
type: chore
status: review
priority: low
labels: [decision, docs]
---
From the October 2026 review ([[Project/Review-2026-10]], §13.7). Missing: a tutorial (Getting started hands over to the reference after one program), a "Why Myla" page, a standard-library reference with a runnable snippet per function, and a test that the snippets in the docs still compile and print what they say. The website plan ([[MYLA-159]]) wants a gamified tutorial too.

## Question

Where is the tutorial written, when, and how are the docs kept correct?

## Options

- **A. In the wiki now**: 10–15 Markdown chapters following the examples' reading order, which the website imports later; a doc-snippet burn test (extract every `myla` block, check it, compare its printed output with the comment) first, to protect everything after it.
- **B. Wait for the website** and write the tutorial there, interactive from the start.
- **C. Reference first**: generate the standard-library reference from `#test` cases and signatures, the tutorial later.

## Recommendation

**The doc-snippet test now; the tutorial in the wiki after the ergonomics round** ([[MYLA-215]], [[MYLA-203]], [[MYLA-204]]), since those decisions change the code every chapter shows; the website reuses the chapters. The generated reference comes with the standard-library round ([[MYLA-211]]).

## Decision

**D114 (2026-11-01): the recommendation.** Implementation: [[MYLA-233]] (doc-snippet test), [[MYLA-234]] (tutorial, Why Myla); the generated reference with [[MYLA-189]].

- [x] Decided, and recorded on [[Project/Decisions]]
- [x] The implementation tasks created or updated to match
