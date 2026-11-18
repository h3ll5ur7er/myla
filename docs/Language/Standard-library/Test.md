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
| `temp_dir() -> str` | A fresh, empty directory for the running case under `$TMPDIR` (else `/tmp`; on Windows `%TEMP%`, std.fs's `temp_root`, [[MYLA-728]]); each call gives another, and the runner removes them all when the case ends, passed or failed. A runtime error outside a case (`myla run`). It is `std.fs`'s `make_temp_dir_in` in the case's scratch root: `d` and 16 random hexadecimal digits, mode 0700 ([[MYLA-339]]) |
| `temp_file() -> str` | A fresh, empty file for the running case, the same way (`make_temp_file_in`: `f` and 16 random digits, mode 0600), removed with the case's directories; a runtime error outside a case |
| `program() -> str` | The path of the project's program, which `myla test` builds before the files of `tests/` run ([[MYLA-306]]); a runtime error elsewhere |

The printable primitives count as implementing `Format` for a bound (`expect_eq(3, 4)`); a value `==` doesn't compare (an `Option`, a `Result`, a list) is checked with `expect` on a `match`, or taken apart with `?` in a test function returning `Result<(), E>`. The module's other public functions (`Case`, `case_index`, `from_index`, `record_head`, `reporting`, `child_done`, `case_begin`, `case_end`, `cut_run`, `run_in_children`, `report_inline`, `summary`, `end`, `case_detail`, `case_outcome`, `case_lines`, `fail_line`, `Record`, `record_in`, `repr_str`, `repr_float`, `without_module_ids`, `tool_mode`, `watch_mode`, `timed_out`, `Timed`, `output_within`) are the runner of the harness `myla test --native` builds ([[Language/Attributes-and-testing#native-runs]]), not for programs: a child reports its case in a record on stderr framed with the run's nonce (D191, [[MYLA-547]]), `\u{1}myla-<nonce>\u{1}` then `P:0;` (passed), `F:<n>;<detail>`, `E:<n>;<message>` (a runtime error, which std.rt writes) or `X:<status>;` (an `exit`), and `B:0;` on both streams before each case of a run `--from <n>`. A case runs for at most MYLA_TEST_TIMEOUT's seconds, which `myla test --timeout` sets (D259): `output_within` runs a child so, its process group killed on Linux as it ends or passes the limit, `myla test` runs a wasm32 harness through it too (the limit counted from each `B:0;`). On Linux the runner starts a watcher beside the cases, `<harness> --watch-groups` (`watch_mode`, [[MYLA-819]]): in a group of its own, not dying with the runner, it is told on its input which case's group runs (`output_within`'s `watch`), and when that input ends, the runner having died, it kills that group, whose processes the case's own death left.

**The test tool** ([[MYLA-727]]). A case that starts processes needs a child every target with processes has, Windows too, where Linux's `cat`, `sh` and `head` aren't: the program that runs the cases, in a mode of its own, `<program> --test-tool <step>…`. Natively it is the harness, whose runner gives each case's child its own path as `MYLA_TEST_TOOL`; interpreted it is `myla` itself (`myla --test-tool …`); both call `tool_mode` first, and a case finds the program with the primitive `__test_tool()` ([[Language/Standard-library/Rt]]), under `MYLA_TEST_EMULATOR`'s emulator where the harness runs under one (qemu-user starts no child under itself). Its steps run in order, then it ends with 0: `cat` (its input to its output, a piece at a time, to the end), `upper` and `a-for-nul` (the same, ASCII's lowercase letters uppercase, each zero byte an `a`), `head <n>` (the first `n` bytes), `count` (the input's length in bytes and a newline, as `wc -c`), `line` (a line of the input without its newline), `out <text>` and `err <text>`, `zeros <n>` and `err-zeros <n>` (zero bytes), `sleep <ms>` and `exit <n>`; a write to a pipe nobody reads ends it quietly, as by SIGPIPE (D146). std.process's own cases start it (`tool` in [[lib/std/process.my]]).
