# std.args

Command-line arguments, declared ([[MYLA-333]]). A `Spec` says what a program's arguments are; `parse` reads them into an `Args`, which the program asks by name. Myla has no references or reflection, so the names are the link between the two. The module imports `std.option`, `std.io` and `std.process`.

```myla
import std.args as args
from std.args import Spec

fun cli() -> Spec {
    let build = (args.spec("build", "Compiles a program.")
        .flag("release", 'r', "optimize")
        .positional("file", "the program"))
    return (args.spec("tool", "Builds things.")
        .flag("verbose", 'v', "say more")
        .option("out", 'o', "FILE", "where to write", Some("a.out"))
        .option("define", 'D', "NAME", "define a name")
        .command("build", build))
}

fun main() {
    match args.parse(cli(), ["-v", "-DX", "--define=Y", "build", "-r", "main.my"]) {
        Ok(a) => {
            print(a.flag("verbose"))
            print(a.get_or("out", "?"))
            print(a.all("define").len())
            if let Some((name, sub)) = a.command() {
                print(f"{name} {sub.get_or("file", "?")} {sub.flag("release")}")
            }
        }
        Err(e) => print(f"{e}")
    }
    match args.parse(cli(), ["--frob"]) {
        Ok(_) => print("parsed")
        Err(e) => print(f"{e}")
    }
    match args.parse(cli(), ["--help"]) {
        Ok(_) => print("parsed")
        Err(e) => print(e.message())
    }
}
// output:
// true
// a.out
// 2
// build main.my true
// unknown option '--frob'
// Builds things.
//
// usage: tool [options] [<command>]
//
// Options:
//   -v, --verbose      say more
//   -o, --out FILE     where to write (default: a.out)
//   -D, --define NAME  define a name
//   -h, --help         print this help
//
// Commands:
//   build              Compiles a program.
```

## The spec

`spec(name: str, about: str = "") -> Spec` is a spec without arguments: `name` is the program's name in the help, `about` the help's first line. Each method gives back a new spec with one argument more, so a spec is a chain of calls; in parentheses, as a line can't start with `.`.

| Method | Declares |
| --- | --- |
| `flag(name: str, short: char = '\0', help: str = "")` | A flag, `--name`, and `-c` with a `short` other than `'\0'` |
| `option(name: str, short: char = '\0', value: str = "VALUE", help: str = "", default: Option<str> = None)` | An option with a value: `--name v`, `--name=v`, `-c v`, `-cv`. `value` names the value in the help; `default` is what `get` gives when the option isn't given |
| `positional(name: str, help: str = "", required: bool = true)` | The next positional argument, in the order they are declared |
| `many(name: str, help: str = "")` | The arguments past the positionals, none or many |
| `command(name: str, sub: Spec)` | A subcommand: the first argument past the positionals, if it is `name` and comes before `--`; the arguments after it are `sub`'s, and the help lists it with `sub`'s `about` |
| `usage() -> str` | The usage line, `usage: prog [options] <input> [<mode>] [<rest>...]` |
| `help() -> str` | The help text: `about`, the usage line, then the arguments, the options and the commands, each with its help in one aligned column, without a newline at the end |

A spec has either `many` or commands: with `many`, every argument past the positionals is one of its. A short name is one ASCII character.

`check_name` and `check_option`, methods of `Spec`, are the declaring methods' own checks (the panics below), public only because a method can't be private yet ([[MYLA-433]]); a program has no need of them.

A spec that can't be parsed is a mistake in the program, so the method that would make it panics, naming the argument ([[MYLA-426]]): a name declared twice (options, positionals and `many` share the names `Args` is asked by: `args: 'out' is declared twice`), a short name given twice (`args: '-v' is declared twice (--verbose and --very)`), an empty name or one that starts with `-` or holds `=`, an option's name with a space or a control character (it is typed as one argument; a positional's name is only shown, `<lib dir>`), a short name that isn't a printed ASCII character or is `-` or `=`, a required positional after an optional one, a positional after `many` or a command (it is read before them, so declared after them it would look like a last argument, `cp <from>... <to>`: `args: the positional 'to' comes after 'many' ('from'), which takes the rest`), `many` twice or together with commands, and a command declared twice or that can't be given, its name empty, starting with `-` or holding a space ([[MYLA-553]]). The panic points at the program's call that made the bad spec, not into std.args: the declaring methods and their checks report their caller's position (`#track_caller`, [[Language/Attributes-and-testing#track_caller]], [[MYLA-435]]), so `.positional("to")` after `.many("from")` fails at that `.positional(`.

## Parsing

`parse(s: Spec, argv: [str]) -> Result<Args, ArgsError>` reads `argv`, the arguments without the program's name: `parse(s, process.args()[1:])`. The forms are getopt's and GNU's:

- `--out x`, `--out=x`, `-o x` and `-ox` give an option its value. The value is the next argument whatever it looks like, so `-o -v` gives `out` the value `-v`.
- Short flags group: `-vq` is `-v -q`, and in `-vox` the `o` takes the rest, `x`.
- Options may come anywhere among the positionals; `--` ends them, and every argument after it is a positional, a command's name too. `-` alone is a positional.
- An option given twice keeps both values. A flag may be given more than once.
- Past a command's name, the arguments are the command's: `tool -v build -r` gives `-v` to `tool` and `-r` to `build`.
- `--help`, and `-h` unless the spec gives `h` to one of its own, give `Err(ArgsError.Help(text))`, the help of the spec or of the command they were given to. The help lists them as `-h, --help`. A spec that declares `help` itself (`flag("help", 'h', "…")`, or an option `--help TOPIC`) takes `--help` as that argument and gives no `Help` error: the program prints `s.help()` itself, which lists its own `--help` in place of the built-in one.

`parse_or_exit(s: Spec, argv: [str]) -> Args` is `parse` for a program that has nothing better to do with an error: for `--help` it prints the help and exits with status 0; for an error it prints `prog: <message>` and the usage line on stderr and exits with status 2. The usage line is that of the spec whose arguments were wrong: `tool build` without its file prints `usage: tool build [options] <file>`.

## The arguments

`Args` is asked by the names of the spec. A name the spec doesn't declare is a mistake in the program, not in its arguments, so it is a panic: `args: 'nme' is not an argument of the spec`. So is asking `get` for a flag or `flag` for an option. It too points at the program's call (`a.get("nme")`, `get_or`, `all`, `flag`, `count`).

| Method | Result |
| --- | --- |
| `flag(name: str) -> bool` | Whether the flag was given |
| `count(name: str) -> int` | How many times the flag was given (`-vvv` is 3) |
| `get(name: str) -> Option<str>` | The option's or positional's value: the last one given, or the option's default, or `None` |
| `get_or(name: str, d: str) -> str` | `get(name)`, or `d` for `None` |
| `all(name: str) -> [str]` | Every value given, in order: an option given several times, the arguments of `many`. With none given, the option's default if it has one |
| `command() -> Option<(str, Args)>` | The command given and its arguments, or `None` |

## Errors

Each error names the argument: an option as it was written (`--out` or `-o`), a positional by its name in the spec, any other argument as it was given. `e.message()` is the sentence, and `ArgsError` implements `Format` with it, so `f"{e}"` shows it.

| Variant | When | `message()` |
| --- | --- | --- |
| `Help(str)` | `--help` or `-h` | The help text |
| `UnknownOption(str)` | An option the spec doesn't declare | `unknown option '--frob'` |
| `MissingValue(str)` | An option at the end, without its value | `option '-o' needs a value` |
| `UnexpectedValue(str)` | A flag given a value, `--verbose=1` | `flag '--verbose' takes no value` |
| `MissingPositional(str)` | A required positional not given | `missing argument <input>` |
| `UnexpectedPositional(str)` | An argument past the positionals, without `many` or commands (after `--`, a command's name too) | `unexpected argument 'x.txt'` |
| `UnknownCommand(str)` | A command the spec doesn't declare | `unknown command 'bild'` |

## Used by

`tools/embed/main.my`, the tool that writes `selfhost/embedded_std.my`, reads its arguments with it (`embed <lib dir> <module file> [--check]`). It prints its own usage line for every error, as it did before.
