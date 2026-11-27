# std.random

Pseudo-random numbers from a seeded generator ([[MYLA-337]]). An `Rng` is a value: a program that wants the same numbers on every run seeds it, `random.seeded(42)`, and one that wants others each time seeds it from the system, `random.from_os()`. It isn't for secrets: anyone who sees four of its numbers can work out the rest. The module imports nothing; [[Language/Standard-library/Uuid]] builds on it.

```myla
import std.random as random
from std.random import Rng

// A game whose dice are a field, so that its methods move them on.
struct Game {
    dice: Rng,
    score: int,
}

impl Game {
    fun roll(var self) -> int {
        let d = self.dice.int_in(1, 7)
        self.score += d
        return d
    }
}

fun main() {
    var r = random.seeded(42)
    print(r.next_u64())
    print(r.int_in(1, 7))
    print(r.float())
    print(r.boolean())
    print(r.shuffled(["a", "b", "c", "d", "e", "f", "g", "h"]).join(""))
    print(r.choice(["red", "green", "blue"]).unwrap_or("-"))
    var copy = r
    print(copy.next_u64() == r.next_u64())

    var g = Game { dice: random.seeded(7), score: 0 }
    let rolls = [g.roll(), g.roll(), g.roll()]
    print(f"{rolls.map((d) => f"{d}").join(" ")}: {g.score}")

    var os = random.from_os()
    let x = os.int_in(0, 100)
    print(x >= 0 && x < 100)
}
// output:
// 1546998764402558742
// 3
// 0.6800434110281394
// true
// acbdgefh
// red
// true
// 5 2 6: 13
// true
```

| Function | Result |
| --- | --- |
| `seeded(seed: uint64) -> Rng` | A generator whose state SplitMix64 makes from `seed`: the same seed gives the same numbers, on every target and in the interpreter. Any seed is good, 0 too |
| `from_os() -> Rng` | A generator seeded from 32 bytes of the system's entropy (`__random_bytes`: getrandom(2), WASI's `random_get`), so other numbers on every run. A system that gives none is a failure, not an `Err`: no program can go on without entropy, as with Rust's `thread_rng` and Python's `os.urandom` (an exception to D164 (3), the owner's choice, [[MYLA-337]]) |

Every method moves the generator on, so each needs a `var` place.

| Method | Result |
| --- | --- |
| `r.next_u64() -> uint64` | The next 64 random bits |
| `r.next_u32() -> uint32` | The next 32 random bits, the high half of a `next_u64` |
| `r.int_in(lo: int, hi: int) -> int` | A number in `lo..hi`, each as likely. `hi` is left out, as in a `for` loop's range: `int_in(1, 7)` is a die. An empty range, `hi <= lo`, is a failure |
| `r.int64_in(lo: int64, hi: int64) -> int64` | The same for `int64`s |
| `r.below(n: uint64) -> uint64` | A number in `0..n`, each as likely; `n` of 0 is a failure |
| `r.float() -> float` | A number in [0, 1): one of the 2^53 multiples of 2^-53 there, each as likely |
| `r.boolean() -> bool` | `true` or `false`, each as likely |
| `r.shuffled<T>(xs: [T]) -> [T]` | The elements of `xs` in a random order, each order as likely; `xs` stays as it was |
| `r.choice<T>(xs: [T]) -> Option<T>` | An element of `xs`, each as likely; `None` when `xs` is empty |

The coin is `boolean`, not `bool`, because `bool` is a keyword. The shuffle is `shuffled`: it returns a new list, as `xs.sorted()` does, since a method of `Rng` can't change a list it is given.

## A generator is a value

A copy of a generator goes on from where the original was, so the two give the same numbers (`copy` above). A function that takes an `Rng` as a parameter draws from its own copy, and the caller's generator doesn't move: the caller gets the same numbers again. Keep the generator in a struct field and draw in a `var self` method (`Game.roll` above), or keep it in a local `var` and draw there. Two parts of a program that want numbers of their own take generators of their own, `seeded(1)` and `seeded(2)`.

`Rng` has `#derive(Eq)`: two generators are equal when they will give the same numbers.

## How it works

The generator is xoshiro256** (Blackman and Vigna, "Scrambled linear pseudorandom number generators", 2018; [prng.di.unimi.it](https://prng.di.unimi.it/)): four 64-bit words of state, a period of 2^256 - 1, and each number made of shifts, rotations, xors and two multiplications. It passes the statistical test suites (BigCrush, PractRand), and its 256 bits of state are plenty for shuffles. PCG64 was the other choice: its state moves on by a 128-bit multiplication, which is four 64-bit ones here, as Myla has no 128-bit integers.

`seeded(n)` fills the four words with four outputs of SplitMix64 started at `n`, as xoshiro's authors recommend: a seed of a few bits still gives a state of well-mixed bits, never all zero. `from_os()` takes the words from the system; an all-zero state, the one xoshiro can't leave, has a chance of 2^-256 and becomes `seeded(0)`.

`int_in`, `int64_in` and `below` have no modulo bias. Taking a random word modulo the size of the range would make some results more likely: with a range of 3 × 2^30, a 32-bit word modulo it lands in the first third half of the time. They use Lemire's method ("Fast random integer generation in an interval", 2019): multiply a random word by the size of the range and keep the high half, the result; when the low half lies among the few values that would favour some results, draw again. That takes a division only in that rare case, and a second draw almost never. `int_in` draws 32 bits (the high half of a `next_u64`), `int64_in` and `below` 64.

`float` is the top 53 bits of a `next_u64` divided by 2^53. `shuffled` is Fisher and Yates's shuffle in Durstenfeld's form: from the last place to the second, swap the element there with one at a place up to it, by `int_in`.

The tests pin the outputs of the reference C code (`splitmix64.c`, `xoshiro256starstar.c`): SplitMix64's first five numbers for the seed 1234567, xoshiro256**'s first ten for the state 1, 2, 3, 4 (as the Rust crate `rand_xoshiro` pins them too), and for `seeded`, `int_in`, `float`, `boolean` and `shuffled`, the numbers of a port of that code. Test functions check that a shuffle is a permutation, that the orders of three elements, the faces of a die and `choice`'s elements come up as often as each other over many draws, and that `int_in` puts a third of its draws in the first third of a range of 3 × 2^30, where a modulo would put half.

## Speed

Measured natively on x86-64, best of five runs (2026-11-08, `a1e0269`):

| Work | Time |
| --- | --- |
| 100 million `next_u64` | 290 ms: 345 million numbers a second (the reference C code at `gcc -O2`: 126 ms, 790 million) |
| 10 million `int_in(1, 7)` | 50 ms: 195 million a second |
