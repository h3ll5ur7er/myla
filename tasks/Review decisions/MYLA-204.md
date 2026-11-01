---
id: MYLA-204
title: "Decision: methods on builtin collections, or free functions only"
type: chore
status: todo
priority: medium
labels: [decision, language, builtins]
---
From the October 2026 review ([[Project/Review-2026-10]], §11.3 and §13.9). Lists, maps and strings use free functions (`push(xs, v)`, `len(s)`, `keys(m)`), while structs, enums and even `impl int32` get methods, and `impl [T]` is forbidden. The review calls this the largest single source of "looks right, fails here", and says half-and-half is the worst option.

## Question

Is there one call style for builtin types, and which?

## Options

- **A. Free functions only.** Keep today's style, and give `xs.push(v)` a diagnostic that names `push(xs, v)`. No language change; the asymmetry with user types stays.
- **B. Method sugar for builtins.** `xs.push(v)` means `push(xs, v)` for the builtin functions whose first parameter is the collection; both styles are valid. Small (front end only), but it makes two styles official.
- **C. Methods on builtin types.** Allow `impl [T]`, `impl Map<K, V>`, `impl str` (in the standard library and in user code), expose the builtins as methods (`var self` where they change the receiver), keep the free functions one release with a deprecation warning, then remove them. One style in the end, and the standard library ([[MYLA-211]]) gets a natural home for `std.str` and friends.

## Recommendation

**C**, and decided before the standard-library round, since it fixes the shape of every new API there. B is an acceptable first step only if the deprecation of the free forms is decided with it.

## Decision

*Open.* The owner's answer goes here and, once given, onto [[Project/Decisions]] as a numbered decision.

- [ ] Decided, and recorded on [[Project/Decisions]]
- [ ] The implementation tasks created or updated to match
