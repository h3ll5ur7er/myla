# std.fmt

Format specs (D139, [[Language/Collections-and-strings]]): the code every runner formats a hole's spec with, so the interpreter and every target print the same bytes, and a helper for a type implementing `Format`.

| Function | Result |
| --- | --- |
| `pad(text: str, spec: str) -> str` | `text` with the fill, alignment (left by default) and width of `spec`: `pad("x", "^5")` is `"  x  "`. A spec that isn't one is a runtime error |
| `parse_spec(s: str) -> Result<Spec, str>` | The spec's parts (`fill`, `align`, `plus`, `alt`, `zero`, `width`, `prec`, `kind`), or why it isn't one |
| `fmt_int(v: int64, bits: int32, signed: bool, spec: str) -> str`, `fmt_float(x: float64, text: str, spec: str) -> str`, `fmt_text(text: str, spec: str) -> str` | A hole's text, as a spec makes it (what the compiler calls) |
