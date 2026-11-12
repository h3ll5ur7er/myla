# std.fmt

Format specs (D139, [[Language/Collections-and-strings]]): the code every runner formats a hole's spec with, so the interpreter and every target print the same bytes, and a helper for a type implementing `Format`.

```myla
import std.fmt as fmt
from std.io import println

struct Money {
    cents: int,
}

impl Format for Money {
    fun format(self, spec: str) -> str {
        let text = f"{self.cents / 100}.{self.cents % 100:02}"
        return fmt.pad(text, spec)
    }
}

fun main() {
    let m = Money { cents: 1205 }
    println(f"[{m}] [{m:>8}] [{m:*^9}]")
    match fmt.parse_spec("+08.2") {
        Ok(sp) => println(f"width {sp.width}, precision {sp.prec}, {fmt.spec_need(sp, 0)}")
        Err(e) => println(e)
    }
}
// output:
// [12.05] [   12.05] [**12.05**]
// width 8, precision 2, needs a float
```

| Function | Result |
| --- | --- |
| `pad(text: str, spec: str) -> str` | `text` with the fill, alignment (left by default) and width of `spec`: `pad("x", "^5")` is `"  x  "`. A spec that isn't one is a runtime error. A gap of more than 16 characters, as a number's zeros, is filled in bulk by std.str's `repeat` ([[MYLA-546]]) |
| `parse_spec(s: str) -> Result<Spec, str>` | The spec's parts (`fill`, `align`, `plus`, `alt`, `zero`, `width`, `prec`, `kind`), or why it isn't one |
| `spec_need(sp: Spec, class: int32) -> str` | What `sp` needs that a value of the class isn't (0 an integer, 1 a float, 2 text: `str`, `char`, `bool`), as the checker's message ends: `"needs a float"` for a precision on an integer; `""` when it fits |
| `fmt_int(v: int64, bits: int32, signed: bool, spec: str) -> str`, `fmt_float(x: float64, text: str, spec: str) -> str`, `fmt_text(text: str, spec: str) -> str` | A hole's text, as a spec makes it (what the compiler calls) |
