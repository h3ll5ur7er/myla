title: The Multiverse
emoji: 🌀
tagline: A bonus chapter. Strings, sorting and format specs, one universe at a time.

The portal is open, and every exercise lands you somewhere else: a Witcher's notice board, a castle with moving staircases, a Stargate, a city run by one operating system. The constant across universes is the standard library.

- Strings have methods for nearly everything: `s.trim()`, `s.to_lower()`, `s.split(",")`, `s.replace(a, b)`, `s.starts_with(p)`, and `for c in s` visits the characters.
- Lists sort themselves: `xs.sorted()` gives a new, sorted list, `xs.sort()` sorts a `var` in place, `xs.reversed()` turns one around, and slices like `xs[:3]` and `xs[^1]` pick parts.
- A hole in an f-string takes a format spec after a colon: `{n:03}` pads with zeros, `{x:.2}` rounds, `{n:x}` is hexadecimal, `{s:>8}` aligns right.
- `char`s know what they are: `c.is_alpha()`, `c.is_digit()`, `c.to_lower()`.

See [[Language/Standard-library/Str]], [[Language/Standard-library/List]] and [[Language/Collections-and-strings]]. Engage.
