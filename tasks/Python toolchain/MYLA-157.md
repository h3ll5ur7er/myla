---
id: MYLA-157
title: A ? failing inside a list or map literal leaks the half-built literal (both backends)
type: bug
status: done
priority: medium
labels: [python-backend, selfhost, memory]
---
[[MYLA-4]] notes that in the Python backend, a `?` that returns early from inside a list or map literal leaves the literal's elements allocated so far unreleased; no task tracks it, and it wasn't measured. (The self-hosted backend's leaks went with [[MYLA-22]].)

**Confirmed by the October 2026 review ([[Project/Review-2026-10]]), in both backends.** 900,000 iterations of `let xs = [f"...", fails(i)?]` reach 117 MB peak RSS against 13 MB with the `?` hoisted out of the literal; 100k/300k/900k iterations grow linearly (27/80/240 MB, about 115 bytes each), with the same numbers for the Python backend's binary. The IR shows why (`--emit-ir`): the fresh cell (`%t = rt __alloc`) is registered as an owning temporary only after every element is stored, so the failure block drops the staged elements but never frees the cell or the strings already moved into it (`moved`); the verifier can't see it because the cell isn't in a slot yet. Fix in [[selfhost/lower.my]] (`list_lit`, `map_lit`): own the fresh cell before evaluating the elements; the same in [[src/myla/compiler/codegen_x86.py]].

- [x] Reproduce with a stress program that fails a `?` inside a literal many times, measuring memory: it leaks, in both backends
- [x] Own the fresh cell before the elements in both backends; release it on the early way out
- [x] A `?`-in-literal case in `test_stress_programs_reclaim_memory` (both backends and the codegen gate, with the 30 MB bound)

## Evidence

- Self-hosted: `list_lit` owns the cell from the start, its length counting the elements stored so far (the map literal did already). Python backend: the half-built list or map and the stored elements' temporaries are staged drops of an early return.
- `STRESS_TRY_IN_LITERAL_SRC` (1.2M failing literals with a 1 KB string element): the Python backend's binary ran out of its 1 GiB arena before and passes after (`test_try_in_a_literal_releases_it`); the self-hosted binary peaked at 618 MB before and 10 MB after (in `test_stress_programs_reclaim_memory`, under its 30 MB bound).
- Unit 622, integration 2, burn 826 (5 skipped) and the extension's 54 tests pass on commit 12f6e94; the bootstrap reaches its byte-identical fixed point (6,153,392 bytes).
