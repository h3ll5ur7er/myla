# std.char

Character classes, case and digits, as methods on `char` ([[MYLA-322]]). They are ASCII (D164 (2)): a character outside ASCII is in no class, and the case mappings leave it as it is. [[MYLA-320]] will import the module into every program; until then a program imports it (`import std.char`, or `from std.char import from_digit`, which brings the methods too). It imports nothing itself.

```myla
from std.char import from_digit

fun main() {
    var letters = 0
    var digits = 0
    for c in "Hello, World 42".chars() {
        if c.is_alpha() {
            letters += 1
        } else if c.is_digit() {
            digits += 1
        }
    }
    print(f"{letters} letters, {digits} digits")
    print('q'.to_upper())
    print('\t'.is_space())
    match 'f'.to_digit(16) {
        Some(d) => print(d)
        None => print("not a hex digit")
    }
    match from_digit(11, 16) {
        Some(c) => print(c)
        None => print("no such digit")
    }
}
// output:
// 10 letters, 2 digits
// Q
// true
// 15
// b
```

| Method or function | Result |
| --- | --- |
| `c.is_digit()` | `0` to `9` |
| `c.is_alpha()` | `a` to `z` and `A` to `Z` |
| `c.is_alnum()` | A letter or a digit |
| `c.is_space()` | Space, tab, line feed, vertical tab, form feed and carriage return: C's `isspace`, and the set `std.str` trims (Rust's `is_ascii_whitespace` leaves out the vertical tab) |
| `c.is_upper()`, `c.is_lower()` | `A` to `Z`; `a` to `z` |
| `c.to_upper()`, `c.to_lower()` | The letter in the other case; any other character as it is |
| `c.to_digit(radix: int) -> Option<int>` | The digit's value: `0` to `9`, then `a` to `z` or `A` to `Z` for 10 to 35; `None` if `c` isn't a digit of the radix |
| `from_digit(d: int, radix: int) -> Option<char>` | The character for the digit `d`, lower case past 9; `None` if `d` is negative or not below `radix` |

A radix outside 2 to 36 is a runtime error (`to_digit: radix must be from 2 to 36, not 37`), as in Rust. `from_digit` is a function, not a method: Myla has no associated functions.

The short names (`is_digit`, `is_alpha`, `to_upper`) are the roadmap's, for ASCII the only classes there are; Rust spells them `is_ascii_digit`, `is_ascii_alphabetic`, `to_ascii_uppercase`, and its `is_digit` takes a radix.
