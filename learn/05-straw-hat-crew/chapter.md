title: The Straw Hat Crew
emoji: 🏴‍☠️
tagline: Structs, enums, methods and match. Assemble your crew.

A captain alone doesn't sail far. Structs gather values into one, enums say "one of these", and methods give your types their own moves.

- `struct Pirate { name: str, bounty: int64 }` defines a type; `Pirate { name: "Zoro", bounty: 1_111_000_000 }` makes one.
- `impl Pirate { fun poster(self) -> str { … } }` adds methods, called as `p.poster()`. A method that changes its value takes `var self`.
- `enum Fruit { Gomu, Mera }` is one of its variants; a variant may carry values: `Armament(int)`.
- `match` takes an enum apart, and must cover every variant.
- `impl Format for Pirate` makes a value printable with `print` and in f-strings.

See [[Language/Structs-enums-and-match]] and [[Language/Methods-and-traits]]. I'm gonna be King of the Pirates!
