title: Infinity Stones
emoji: 💎
tagline: Lists, maps and strings. Collect all six.

Six stones, scattered across the universe; six kinds of collection work, scattered across your programs.

- A list `[1, 2, 3]` has the type `[int]`. `xs.push(v)` adds, `xs.len()` counts, `xs[0]` reads.
- Lists are **values**: assigning or passing one gives a copy (a cheap one). A parameter can't be changed, so copy it into a `var` first.
- `xs.map(f)`, `xs.filter(f)`, `xs.fold(start, f)` take functions: `xs.filter((x: int) => x > 0)`.
- A map `["a": 1]` has the type `[str: int]`; `m[k] = v` sets, `m.get_or(k, 0)` reads with a default.
- Strings have `split`, `join`, `to_upper`, `trim`, `contains` and friends.

See [[Language/Collections-and-strings]] and the [[Language/Standard-library|reference]] for every method. Perfectly balanced, as all things should be.
