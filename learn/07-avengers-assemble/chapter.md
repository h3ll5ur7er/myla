title: Avengers, Assemble
emoji: 🛡️
tagline: Traits, generics and operators. Earth's mightiest abstractions.

Different heroes, one team: a trait says what a type can do, and generic code works with any type that can.

- `trait Hero { fun name(self) -> str }` lists methods; `impl Hero for Thor { … }` provides them. There are no default bodies.
- `fun assemble<T: Hero>(h: T)` works for every `T` that implements `Hero`: the bound is checked once, and the function compiled for each type it is used with.
- Structs can be generic too: `struct Pair<T> { first: T, second: T }`.
- Operators are traits: `impl Add for Power` gives `a + b`, and `impl Mul<int> for Power` gives `p * 3` (D200).

See [[Language/Methods-and-traits]] and [[Language/Generics]]. Whatever it takes.
