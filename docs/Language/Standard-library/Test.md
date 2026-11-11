# std.test

What a test function needs beyond `#test` (D162, [[MYLA-304]], [[Language/Attributes-and-testing#test-functions]]). Every failure is a runtime error, as `assert`'s is: the case fails the way a program fails, and `myla test` is the one place that goes on after one.

`myla test file.my` runs the test function below (`PASS  saves_one_word_a_line`), interpreted and with `--native`; `myla run` runs `main`, where an expectation that holds does nothing and one that fails ends the program.

```myla
import std.fs as fs
import std.test as test
from std.io import println

// The words of `text`, one a line, written to `path`.
fun save_words(path: str, text: str) -> Result<(), fs.IoError> {
    var sb = StringBuilder()
    for w in text.split(" ") {
        if w != "" {
            sb.append(w)
            sb.append("\n")
        }
    }
    return fs.write_to_file(path, sb.build())
}

#test
fun saves_one_word_a_line() -> Result<(), fs.IoError> {
    let path = test.temp_dir() + "/words.txt"
    save_words(path, "to  be or")?
    let back = fs.read_to_string(path)?
    test.expect_eq(back, "to\nbe\nor\n")
    test.expect_ne(back.len(), 0)
    test.expect(fs.exists(path), "the file is there")
    return Ok(())
}

fun main() {
    test.expect_eq(2 + 2, 4)
    println("outside a case an expectation that holds does nothing")
}
// output:
// outside a case an expectation that holds does nothing
```

| Function | Meaning |
| --- | --- |
| `expect(cond: bool, msg: str = "expectation failed")` | Fails the case with `msg` unless `cond` holds |
| `expect_eq<T: Eq + Format>(got: T, want: T)` | Fails with `expected <want>, got <got>` unless they are equal; `T` is a type `==` compares and `{}` shows: an integer, float, `char`, `bool`, `str`, or a type implementing `Eq` and `Format` |
| `expect_ne<T: Eq + Format>(got: T, other: T)` | Fails with `expected two different values, both are <got>` when they are equal |
| `fail(msg: str)` | Fails the case with `msg` |
| `temp_dir() -> str` | A fresh, empty directory for the running case under `$TMPDIR` (else `/tmp`); each call gives another, and the runner removes them all when the case ends, passed or failed. A runtime error outside a case (`myla run`). It is `std.fs`'s `make_temp_dir_in` in the case's scratch root: `d` and 16 random hexadecimal digits, mode 0700 ([[MYLA-339]]) |
| `temp_file() -> str` | A fresh, empty file for the running case, the same way (`make_temp_file_in`: `f` and 16 random digits, mode 0600), removed with the case's directories; a runtime error outside a case |
| `program() -> str` | The path of the project's program, which `myla test` builds before the files of `tests/` run ([[MYLA-306]]); a runtime error elsewhere |

The printable primitives count as implementing `Format` for a bound (`expect_eq(3, 4)`); a value `==` doesn't compare (an `Option`, a `Result`, a list) is checked with `expect` on a `match`, or taken apart with `?` in a test function returning `Result<(), E>`. The module's other public functions (`Case`, `case_index`, `from_index`, `child_done`, `case_begin`, `case_end`, `cut_run`, `run_in_children`, `report_inline`, `summary`, `end`, `case_detail`, `case_outcome`, `case_lines`, `repr_str`, `repr_float`, `without_module_ids`) are the runner of the harness `myla test --native` builds ([[Language/Attributes-and-testing#native-runs]]), not for programs.
