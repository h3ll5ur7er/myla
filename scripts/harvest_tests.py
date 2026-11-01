#!/usr/bin/env python3
"""harvest_tests.py: generate `#test` cases for the self-hosted compiler
(MYLA-184, D109).

The self-hosted toolchain is correct as far as anyone can tell: it agrees with
the Python toolchain on the whole test corpus and compiles itself to a
byte-identical fixed point. So whatever its functions return today is a valid
expected result, and recording calls gives regression tests for free.

    scripts/harvest_tests.py record   # run the workloads, keep the calls (resumes;
                                      # FRESH=1 starts over, ONLY=regex selects)
    scripts/harvest_tests.py merge    # merge the parts of a stopped `record`
    scripts/harvest_tests.py generate # run functions with state on factory receivers
    scripts/harvest_tests.py write    # write the chosen cases into selfhost/
    scripts/harvest_tests.py validate # drop every case a runner rejects

`record` runs the self-hosted CLI (`selfhost/main.my`) in the Python
interpreter over workloads (`check`, `build`, `run` and `test` of the
examples, `check` of the error corpus). A hook on function entry and return
records each call of a function in `selfhost/` whose arguments and result
print as Myla expressions under a size limit (printed from the function's
signature types, so a `char` prints as a character and a struct as a struct
literal in the names the module itself uses). A call during which the program
does I/O (output, files, processes, arguments) is not kept.

`write` keeps a few small, distinct cases per function that has none yet and
writes them as `#test(args)[expected]` lines above it. `validate` runs both
test runners (`python3 myla.py test` and `build/myla test`) on every changed
file and removes each case one of them rejects or fails, until both pass.
The cases record what the compiler does today: read them before committing.
"""

from __future__ import annotations

import base64
import json
import math
import pickle
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

from myla import ast, loader                              # noqa: E402
from myla.interpreter import (EnumValue, Interpreter, ListValue, MapValue,  # noqa: E402
                              StructValue, TupleValue, _copy)
from myla.types import (BoolType, CharType, EnumType, FloatType, IntType,  # noqa: E402
                        ListType, MapType, StrType, StructType, TupleType,
                        TypeParam, check)

SELFHOST = os.path.join(REPO, "selfhost")
ENTRY = os.path.join(SELFHOST, "main.my")
STDLIB = os.path.join(REPO, "src", "myla")
STATE = os.path.join(REPO, "build", "harvest")
RECORDS = os.path.join(STATE, "records.json")
ARGS = os.path.join(STATE, "args.json")             # arguments beside state, as values
GENERATED = os.path.join(STATE, "generated.json")   # cases run on factory receivers

MAX_CASE = 220          # characters of one case's arguments and result together
MAX_DISTINCT = 40       # distinct calls kept per function while recording
CASES_PER_FUNCTION = 3
GENERATED_PER_FUNCTION = 1   # a case with factory-built state costs a factory call in each runner
WORKLOAD_SECONDS = 240
MAX_ARGSETS = 8         # recorded argument lists kept per function with state parameters
MAX_GENERATED = 400     # characters of a generated case's other arguments and result
CALL_SECONDS = 3

# The compiler's state objects can't be written as literals, and its AST
# values only at great length; a factory in the parser or the type's own
# module builds one (MYLA-184): from each source of a snippet set, without
# arguments, or from fixed arguments. A parameter of such a type (a method's
# receiver, or any other) takes the factory's call in a generated case.
FACTORIES = {
    "Parser": ("parser.my", "parser_on", "fragments"),
    "Checker": ("checker.my", "checker_on", "programs"),
    "Interp": ("interp.my", "interp_on", "programs"),
    "CodeGen": ("codegen.my", "codegen_on", "programs"),
    "Lower": ("lower.my", "lower_on", []),
    "Norm": ("anf.my", "new_norm", [0]),
    "Expr": ("parser.my", "expr_of", "exprs"),
    "Stmt": ("parser.my", "stmt_of", "stmts"),
    "TypeExpr": ("parser.my", "type_expr_of", "types"),
    "Block": ("parser.my", "block_of", "blocks"),
    "Pattern": ("parser.my", "pattern_of", "patterns"),
    "FunData": ("parser.my", "fun_of", "funs"),
}

# The sources the factories build from, one line each so a case stays one
# line; the sets take turns together (the k-th source of each).
SNIPPETS = {
    "fragments": ["1 + 2 * 3", "f(x, 2)", "a.b[0]", "let x = 1", "[int]", "Some(n)",
                  "fun f(n: int) -> int { return n * 2 }", "struct P { x: int, y: int }",
                  "enum E { A, B(int) }", "fun main() { print(1 + 2) }",
                  "const N: int = 4; fun g() -> int { return N }",
                  "fun h(xs: [int]) -> int { var t = 0; for x in xs { t = t + x }; return t }",
                  "match e { A => 0, B(n) => n }", "impl C { fun get(self) -> int { return self.n } }",
                  "(x: int) => x + 1", "import a.b as c"],
    "programs": ["fun f(n: int) -> int { return n * 2 }", "struct P { x: int, y: int }",
                 "enum E { A, B(int) }", "fun main() { print(1 + 2) }",
                 "const N: int = 4; fun g() -> int { return N }",
                 "fun h(xs: [int]) -> int { var t = 0; for x in xs { t = t + x }; return t }",
                 "struct P { x: int }; fun get(p: P) -> int { return p.x }",
                 "fun s(a: str) -> str { return a + \"!\" }",
                 "enum E { A, B(int) }; fun v(e: E) -> int { return match e { A => 0, B(n) => n } }",
                 "struct C { n: int }; impl C { fun get(self) -> int { return self.n } }",
                 "fun m() -> [str: int] { var d: [str: int] = [:]; d[\"a\"] = 1; return d }",
                 "fun k(f: (int) -> int) -> int { return f(2) }; fun z() -> int { return k((x: int) => x + 1) }"],
    "exprs": ["1 + 2 * 3", "f(x, 2)", "a.b[0]", "Some(n)", "[1, 2, 3]", "x |> f(_, 2)",
              "-n * 2", "\"s\" + t", "p.x == 3 && !done", "E.B(4)", "(a, 'c')", "[\"k\": 1]"],
    "stmts": ["let x = 1", "var y: int = 2", "x = x + 1", "return a", "while i < 3 { i = i + 1 }",
              "for v in xs { print(v) }", "if a { b() } else { c() }", "print(1)"],
    "types": ["int", "[str]", "[str: int]", "(int, bool)", "Option<P>", "(int) -> bool", "uint8", "Box<T>"],
    "blocks": ["{ return 1 }", "{ print(1); print(2) }", "{ let x = 1; return x }", "{ }"],
    "patterns": ["Some(x)", "E.B(n)", "(a, _)", "P { x, y: 0 }", "3", "_", "\"s\"", "None"],
    "funs": ["fun f(n: int) -> int { return n * 2 }", "fun g() { print(1) }",
             "fun h(xs: [int]) -> int { return len(xs) }", "fun k(a: str, b: bool) -> str { return a }"],
}


# primitives whose result or effect depends on the world outside the call
IMPURE = {"print", "__write", "__exit", "__args", "__read_file", "__read", "__poll",
          "__io_errno", "__getcwd", "__write_file", "__list_dir", "__stat", "__mkdir",
          "__unlink", "__rmdir", "__rename", "__run", "__run_errno", "__run_exit_code",
          "__run_signal", "__run_stderr", "__task_cancelled"}


class Unprintable(Exception):
    pass


# -- printing values as Myla expressions ---------------------------------------

class Printer:
    """Prints a runtime value as a Myla expression of a static type, in the
    names one module uses (`names`: qualified name -> the module's own)."""

    def __init__(self, checker, names: dict[str, str]):
        self.checker = checker
        self.names = names
        self.budget = 0

    def show(self, value, t, budget: int) -> str:
        self.budget = budget
        return self._show(value, t)

    def _emit(self, text: str) -> str:
        self.budget -= len(text)
        if self.budget < 0:
            raise Unprintable("too long")
        return text

    def _name(self, qualified: str) -> str:
        local = self.names.get(qualified)
        if local is None:
            raise Unprintable(f"'{qualified}' has no name in the module")
        return local

    def _show(self, v, t) -> str:
        if isinstance(t, IntType):
            if not isinstance(v, int) or isinstance(v, bool):
                raise Unprintable("int")
            return self._emit(str(v))
        if isinstance(t, BoolType):
            return self._emit("true" if v else "false")
        if isinstance(t, FloatType):
            return self._emit(_float_text(v, t.width))
        if isinstance(t, CharType):
            return self._emit("'" + _escape_char(v, "'") + "'")
        if isinstance(t, StrType):
            return self._emit('"' + "".join(_escape_char(ord(c), '"') for c in v) + '"')
        if isinstance(t, ListType):
            if not isinstance(v, ListValue):
                raise Unprintable("list")
            return self._seq("[", [(e, t.elem) for e in v.elems], "]")
        if isinstance(t, MapType):
            if not isinstance(v, MapValue):
                raise Unprintable("map")
            if not v.entries:
                return self._emit("[:]")
            parts = []
            self._emit("[")
            for k, val in v.entries.items():
                parts.append(self._show(k, t.key) + self._emit(": ") + self._show(val, t.value))
                self._emit(", ")
            return "[" + ", ".join(parts) + "]"
        if isinstance(t, TupleType):
            if not isinstance(v, TupleValue):
                raise Unprintable("tuple")
            text = self._seq("(", list(zip(v.elems, t.elems)), ")")
            return text[:-1] + ",)" if len(t.elems) == 1 else text
        if isinstance(t, StructType):
            if not isinstance(v, StructValue) or t.name not in self.checker.structs:
                raise Unprintable("struct")
            subst = self._subst(t.name, t.args, self.checker.struct_decls)
            fields = self.checker.structs[t.name]
            head = self._emit(self._name(t.name) + " {")
            parts = []
            for fname, ftype in fields.items():
                parts.append(self._emit(f" {fname}: ") + self._show(v.fields[fname], _apply(ftype, subst)))
            return head + ",".join(parts) + self._emit(" }")
        if isinstance(t, EnumType):
            if not isinstance(v, EnumValue):
                raise Unprintable("enum")
            if t.name == "Option":
                if v.variant == "None":
                    return self._emit("None")
                return self._emit("Some(") + self._show(v.payload[0], t.args[0]) + self._emit(")")
            if t.name == "Result":
                inner = t.args[0] if v.variant == "Ok" else t.args[1]
                return self._emit(v.variant + "(") + self._show(v.payload[0], inner) + self._emit(")")
            if t.name not in self.checker.enums:
                raise Unprintable("enum")
            subst = self._subst(t.name, t.args, self.checker.enum_decls)
            head = self._emit(self._name(t.name) + "." + v.variant)
            ptypes = self.checker.enums[t.name][v.variant]
            if not ptypes:
                return head
            return head + self._seq("(", [(p, _apply(pt, subst)) for p, pt in zip(v.payload, ptypes)], ")")
        raise Unprintable(type(t).__name__)

    def _seq(self, open_: str, items: list, close: str) -> str:
        self._emit(open_ + close)
        parts = []
        for value, t in items:
            parts.append(self._show(value, t))
            self._emit(", ")
        return open_ + ", ".join(parts) + close

    def _subst(self, name: str, args: tuple, decls: dict) -> dict:
        decl = decls.get(name)
        params = list(getattr(decl, "type_params", []) or []) if decl is not None else []
        return {p: a for p, a in zip(params, args)}


def _apply(t, subst: dict):
    if not subst:
        return t
    if isinstance(t, TypeParam):
        return subst.get(t.name, t)
    if isinstance(t, ListType):
        return ListType(_apply(t.elem, subst))
    if isinstance(t, MapType):
        return MapType(_apply(t.key, subst), _apply(t.value, subst))
    if isinstance(t, TupleType):
        return TupleType(tuple(_apply(e, subst) for e in t.elems))
    if isinstance(t, StructType):
        return StructType(t.name, tuple(_apply(a, subst) for a in t.args))
    if isinstance(t, EnumType):
        return EnumType(t.name, tuple(_apply(a, subst) for a in t.args))
    return t


_SIMPLE_ESCAPES = {10: "\\n", 9: "\\t", 13: "\\r", 0: "\\0", 92: "\\\\"}


def _escape_char(cp: int, quote: str) -> str:
    if not isinstance(cp, int) or 0xD800 <= cp <= 0xDFFF:
        raise Unprintable("not a Unicode scalar value (a raw byte?)")
    if cp in _SIMPLE_ESCAPES:
        return _SIMPLE_ESCAPES[cp]
    if chr(cp) == quote:
        return "\\" + quote
    if cp < 32 or cp == 127 or not chr(cp).isprintable():
        return "\\u{%x}" % cp
    return chr(cp)


def _float_text(v: float, width: int) -> str:
    if not isinstance(v, float) or math.isnan(v) or math.isinf(v):
        raise Unprintable("float")
    text = repr(v)
    if width == 32:   # the shortest text that rounds to the same float32
        for digits in range(1, 10):
            cand = f"{v:.{digits}g}"
            if struct.unpack("f", struct.pack("f", float(cand)))[0] == v:
                text = cand
                break
    mant, _, exp = text.partition("e")
    if "." not in mant:
        mant += ".0"
    if exp:
        return mant + "e" + str(int(exp))
    return mant


# -- the program under test ------------------------------------------------------

def load():
    """Link and check the self-hosted CLI; return the checker and, for each
    module path, its names (qualified -> the module's own)."""
    names_of: dict[str, dict[str, str]] = {}
    original = loader._Renamer.rename_module

    def capture(self, m):
        names_of[os.path.realpath(m.path)] = {q: n for n, q in m.env_decl().items()}
        return original(self, m)

    loader._Renamer.rename_module = capture
    try:
        program = loader.link(ENTRY, stdlib_root=STDLIB)
    finally:
        loader._Renamer.rename_module = original
    return check(program), names_of


def eligible(checker):
    """id(body) -> the declaration, for the functions and methods of
    `selfhost/` that can carry `#test` cases and have none."""
    out = {}
    for decl in checker.declared_functions():
        path = os.path.realpath(getattr(decl, "source_path", "") or "")
        if not path.startswith(SELFHOST + os.sep) or decl.body is None:
            continue
        sig = checker.functions.get(decl.name)
        if sig is None or sig.ret is None or decl.type_params or decl.is_async:
            continue
        if decl.name.rpartition(".")[0] in checker.actors:
            continue
        if any(a.name == "test" for a in decl.attributes):
            continue
        out[id(decl.body)] = decl
    return out


def workloads() -> list[dict]:
    """Each workload: the CLI's arguments, and optionally its stdin and its
    working directory."""
    examples = sorted(os.path.join("examples", f) for f in os.listdir(os.path.join(REPO, "examples"))
                      if f.endswith(".my"))
    errors = sorted(os.path.join("examples", "errors", f)
                    for f in os.listdir(os.path.join(REPO, "examples", "errors")) if f.endswith(".my"))
    out = []
    for ex in examples:
        out.append({"argv": ["check", ex]})
        out.append({"argv": ["build", ex, "-o", os.path.join(STATE, "bin", os.path.basename(ex)[:-3])]})
        out.append({"argv": ["test", ex]})
    for ex in examples:
        out.append({"argv": ["run", ex]})
    for err in errors:
        out.append({"argv": ["check", err]})
    out.extend(extra_workloads())
    return out


REPL_SESSIONS = [
    "let x = 1 + 2\nx\nfun twice(n: int) -> int {\n    return n * 2\n}\ntwice(x)\n",
    "struct P { x: int, name: str }\nvar p = P { x: 5, name: \"a\" }\np\np.x = 7\np.x\n[1, 2]\n[\"a\": [1]]\n(1, 'c', true)\nSome(1.5)\n",
    "let xs = [1]\nxs[3]\nxs\nfor i in 0..3 {\n    print(i)\n}\ny + 1\nlet x = \"now a string\"\nx\n",
    "from std.num import format_float\nformat_float(0.5)\nenum E { A, B(int) }\nE.B(2)\nmatch E.A {\n    A => 1,\n    B(n) => n,\n}\n",
    "fun bad() -> int {\n    return \"no\"\n}\nlet q = [1, 2, 3]\nq |> len()\n1 / 0\n",
]


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def extra_workloads() -> list[dict]:
    """The REPL, the project commands (`new`, `build`, `run`, `test`,
    `check`, `clean`, `fetch` from a local Git repository) and debug
    information (`build -g`), in projects set up under build/harvest/proj."""
    root = os.path.join(STATE, "proj")
    geo, app = os.path.join(root, "geo"), os.path.join(root, "app")
    _write(os.path.join(geo, "myla.toml"), '[package]\nname = "geo"\nversion = "0.1.0"\n\n[dependencies]\n')
    _write(os.path.join(geo, "src", "geo.my"),
           "pub struct Square {\n    side: int,\n}\n\npub fun area(s: Square) -> int {\n    return s.side * s.side\n}\n")
    _write(os.path.join(app, "myla.toml"),
           '[package]\nname = "app"\nversion = "0.1.0"\n\n[dependencies]\ngeo = { path = "../geo" }\n')
    _write(os.path.join(app, "src", "main.my"),
           "from geo import Square, area\nimport util.strings as strings\n\n#test(2)[4]\nfun sq(n: int) -> int {\n"
           "    return area(Square { side: n })\n}\n\nfun main() {\n    print(strings.shout(\"hi\"))\n"
           "    print(sq(3))\n}\n")
    _write(os.path.join(app, "src", "util", "strings.my"),
           'pub fun shout(s: str) -> str {\n    return s + "!"\n}\n')
    tidy = os.path.join(root, "tidy")
    _write(os.path.join(tidy, "myla.toml"), '[package]\nname = "tidy"\nversion = "0.1.0"\n\n[dependencies]\n')
    _write(os.path.join(tidy, "src", "main.my"), "fun main() {\n    print(1)\n}\n")
    os.makedirs(os.path.join(tidy, "build"), exist_ok=True)
    for made in ("fresh", "freshlib"):      # what `new` makes, made again each round
        shutil.rmtree(os.path.join(root, made), ignore_errors=True)
    out = [{"argv": ["build"], "cwd": app}, {"argv": ["run"], "cwd": app},
           {"argv": ["test"], "cwd": app}, {"argv": ["check"], "cwd": app},
           {"argv": ["clean"], "cwd": tidy}, {"argv": ["new", "fresh"], "cwd": root},
           {"argv": ["new", "--lib", "freshlib"], "cwd": root}]
    lib = os.path.join(root, "greetlib")
    if not os.path.isdir(os.path.join(lib, ".git")):
        _write(os.path.join(lib, "myla.toml"), '[package]\nname = "greet"\nversion = "1.0.0"\n\n[dependencies]\n')
        _write(os.path.join(lib, "src", "greet.my"), 'pub fun hello(n: str) -> str {\n    return "hello " + n\n}\n')
        git = ["git", "-c", "user.name=harvest", "-c", "user.email=harvest@example.invalid"]
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "greet"], ["tag", "v1"]):
            subprocess.run(git + cmd, cwd=lib, check=True, capture_output=True)
    gitapp = os.path.join(root, "gitapp")
    _write(os.path.join(gitapp, "myla.toml"),
           '[package]\nname = "gitapp"\nversion = "0.1.0"\n\n[dependencies]\n'
           f'greet = {{ git = "file://{lib}", tag = "v1" }}\n')
    _write(os.path.join(gitapp, "src", "main.my"),
           'import greet\n\nfun main() {\n    print(greet.hello("you"))\n}\n')
    out += [{"argv": ["fetch"], "cwd": gitapp}]
    out += [{"argv": ["repl"], "stdin": text} for text in REPL_SESSIONS]
    for ex in ("structs", "enums", "maps", "floats", "closures"):
        if os.path.exists(os.path.join(REPO, "examples", ex + ".my")):
            out.append({"argv": ["build", "-g", os.path.join("examples", ex + ".my"),
                                 "-o", os.path.join(STATE, "bin", ex + "-g")]})
    return out


# -- recording ----------------------------------------------------------------

def state_params(checker, decl) -> list[int]:
    """The indices of `decl`'s parameters whose type has a factory."""
    sig = checker.functions[decl.name]
    return [i for i, t in enumerate(sig.params)
            if isinstance(t, StructType) and t.name.split("$")[-1] in FACTORIES]


def record_one(checker, names_of, elig, work: dict, out_path: str) -> None:
    """Run the CLI on a workload with the hooks (in a forked child) and write
    the calls kept to `out_path`: whole calls that print, and for a function
    with state parameters the other arguments, as text and as values."""
    printers = {}
    calls: dict[str, dict[str, None]] = {}
    argsets: dict[str, dict[str, str]] = {}
    stack: list[list] = []
    stateful = {d.name: state_params(checker, d) for d in elig.values()}

    def printer(decl):
        path = os.path.realpath(decl.source_path)
        if path not in printers:
            printers[path] = Printer(checker, names_of.get(path, {}))
        return printers[path]

    orig_run = Interpreter._run
    orig_call = Interpreter._eval_call

    def keep_args(decl, sig, frame, pr, state):
        kept = argsets.setdefault(decl.name, {})
        if len(kept) >= MAX_ARGSETS:
            return
        try:
            budget = MAX_GENERATED
            texts, values = [], []
            for i, (param, ptype) in enumerate(zip(decl.params, sig.params)):
                if i in state:
                    continue
                v = frame.lookup(param.name, _MISSING)
                text = pr.show(v, ptype, budget)
                budget -= len(text) + 2
                texts.append(text)
                values.append(_copy(v))
            key = json.dumps(texts)
            if key not in kept:
                kept[key] = base64.b64encode(pickle.dumps(values)).decode()
        except Exception:   # unprintable, or a value that doesn't pickle
            return

    def run_hook(self, body, frame, path, is_block=True):
        decl = elig.get(id(body))
        if decl is None:
            return orig_run(self, body, frame, path, is_block)
        state = stateful[decl.name]
        sig = checker.functions[decl.name]
        pr = printer(decl)
        if state:
            keep_args(decl, sig, frame, pr, state)
            return orig_run(self, body, frame, path, is_block)
        if len(calls.get(decl.name, ())) >= MAX_DISTINCT:
            return orig_run(self, body, frame, path, is_block)
        try:
            budget = MAX_CASE
            args = []
            for param, ptype in zip(decl.params, sig.params):
                text = pr.show(frame.lookup(param.name, _MISSING), ptype, budget)
                budget -= len(text) + 2
                args.append(text)
        except (Unprintable, KeyError, AttributeError, TypeError):
            return orig_run(self, body, frame, path, is_block)
        entry = [False]
        stack.append(entry)
        try:
            result = orig_run(self, body, frame, path, is_block)
        finally:
            stack.pop()
        if not entry[0]:
            try:
                res = pr.show(result, sig.ret, budget)
            except (Unprintable, KeyError, AttributeError, TypeError):
                return result
            calls.setdefault(decl.name, {})[json.dumps([args, res])] = None
        return result

    def call_hook(self, expr, env):
        callee = expr.callee
        if stack and isinstance(callee, ast.Name) and callee.ident in IMPURE:
            for e in stack:
                e[0] = True
        return orig_call(self, expr, env)

    Interpreter._run = run_hook
    Interpreter._eval_call = call_hook

    def stop(signum, frame_):
        raise _Timeout()

    signal.signal(signal.SIGALRM, stop)
    signal.alarm(WORKLOAD_SECONDS)
    devnull = open(os.devnull, "w")
    stdin = os.path.join(STATE, f"stdin-{os.getpid()}")
    with open(stdin, "w", encoding="utf-8") as fh:
        fh.write(work.get("stdin", ""))
    os.dup2(os.open(stdin, os.O_RDONLY), 0)
    if work.get("cwd"):
        os.chdir(work["cwd"])
    sys.setrecursionlimit(100_000)
    try:
        Interpreter(checker, out=devnull, err=devnull, argv=[ENTRY, *work["argv"]]).run()
    except _Timeout:        # keep what was seen
        pass
    except BaseException:   # an error of the harvester or the program: keep what was seen, say why
        import traceback
        with open(out_path + ".error", "w", encoding="utf-8") as fh:
            fh.write(traceback.format_exc())
    signal.alarm(0)
    os.unlink(stdin)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"calls": {k: list(v) for k, v in calls.items()},
                   "args": {k: [[json.loads(t), b] for t, b in v.items()] for k, v in argsets.items()}}, fh)


class _Impure(BaseException):
    """Raised when a generated call reaches an I/O primitive, before it runs."""


class _Timeout(BaseException):
    """Raised by the alarm; a BaseException so the interpreter's handlers of
    runtime errors don't catch it."""


_MISSING = object()


def cmd_record(jobs: int) -> None:
    os.makedirs(os.path.join(STATE, "bin"), exist_ok=True)
    os.makedirs(os.path.join(STATE, "parts"), exist_ok=True)
    t0 = time.time()
    checker, names_of = load()
    elig = eligible(checker)
    print(f"{len(elig)} functions without cases; loaded in {time.time() - t0:.1f} s", flush=True)
    os.chdir(REPO)
    only = re.compile(os.environ.get("ONLY", ""))
    parts = os.path.join(STATE, "parts")
    # a workload whose part exists already ran: `record` resumes (FRESH=1 starts over)
    if os.environ.get("FRESH"):
        for f in os.listdir(parts):
            os.unlink(os.path.join(parts, f))
    todo = [(i, w) for i, w in enumerate(workloads()) if only.search(" ".join(w["argv"]))
            and not os.path.exists(os.path.join(parts, f"{i:04d}.json"))]
    print(f"{len(todo)} workloads to run", flush=True)
    running: dict[int, tuple] = {}
    while todo or running:
        while todo and len(running) < jobs:
            i, work = todo.pop(0)
            part = os.path.join(STATE, "parts", f"{i:04d}.json")
            pid = os.fork()
            if pid == 0:
                try:
                    record_one(checker, names_of, elig, work, part)
                except BaseException:
                    import traceback
                    traceback.print_exc()
                finally:
                    os._exit(0)
            running[pid] = (i, work, time.time())
        pid, _ = os.wait()
        i, work, started = running.pop(pid)
        print(f"  [{i}] {' '.join(work['argv'][:2])}: {time.time() - started:.0f} s", flush=True)
    merge_parts()
    print(f"done in {time.time() - t0:.0f} s")


def merge_parts() -> None:
    calls: dict[str, list] = {}
    args: dict[str, list] = {}
    for part in sorted(os.listdir(os.path.join(STATE, "parts"))):
        if not part.endswith(".json"):
            continue
        with open(os.path.join(STATE, "parts", part), encoding="utf-8") as fh:
            data = json.load(fh)
        for name, cases in data["calls"].items():
            seen = calls.setdefault(name, [])
            seen.extend(c for c in cases if c not in seen)
        for name, sets in data["args"].items():
            seen = args.setdefault(name, [])
            texts = [t for t, _ in seen]
            seen.extend(a for a in sets if a[0] not in texts and len(seen) < MAX_ARGSETS)
    with open(RECORDS, "w", encoding="utf-8") as fh:
        json.dump(calls, fh, indent=0, sort_keys=True)
    with open(ARGS, "w", encoding="utf-8") as fh:
        json.dump(args, fh, sort_keys=True)
    print(f"{len(calls)} functions with recorded calls, {len(args)} with recorded arguments beside state")


# -- generating on factory receivers ----------------------------------------------

def _local_names(names_of: dict, path: str) -> dict[str, str]:
    """A module's own name -> qualified name (the inverse of `names_of`)."""
    return {local: q for q, local in names_of.get(os.path.realpath(path), {}).items()}


POOL_SIZE = 8


def build_pools(checker, argsets: dict) -> dict:
    """Values per type for arguments nobody recorded: the values recorded
    for other functions' parameters of that type (MYLA-184)."""
    pools: dict = {}
    for name, sets in argsets.items():
        sig = checker.functions.get(name)
        if sig is None:
            continue
        idx = [i for i, t in enumerate(sig.params)
               if not (isinstance(t, StructType) and t.name.split("$")[-1] in FACTORIES)]
        for _, blob in sets:
            values = pickle.loads(base64.b64decode(blob))
            for i, v in zip(idx, values):
                pool = pools.setdefault(sig.params[i], [])
                if len(pool) < POOL_SIZE and v not in pool:
                    pool.append(v)
    return pools


_INTS = [0, 1, 2, 3, 8, 32, -1]
_STRS = ["", "a", "x", "main", "int", "Point", "hello world"]


def pool_values(t, pools: dict, depth: int = 0) -> list:
    """Values of type `t` to try as an argument: recorded ones, else small
    literals for the primitive types and the collections of them."""
    if t in pools:
        return pools[t]
    if isinstance(t, IntType):
        return [v for v in _INTS if t.signed or v >= 0]
    if isinstance(t, StrType):
        return list(_STRS)
    if isinstance(t, BoolType):
        return [True, False]
    if isinstance(t, CharType):
        return [ord(c) for c in "a0 _"]
    if isinstance(t, FloatType):
        return [0.0, 1.5]
    if depth > 1:
        return []
    if isinstance(t, ListType):
        elems = pool_values(t.elem, pools, depth + 1)
        return [ListValue([])] + ([ListValue(elems[:2])] if elems else [])
    if isinstance(t, MapType):
        return [MapValue({})]
    if isinstance(t, EnumType) and t.name == "Option":
        inner = pool_values(t.args[0], pools, depth + 1)
        return [EnumValue("Option", "None", [])] + ([EnumValue("Option", "Some", [inner[0]])] if inner else [])
    if isinstance(t, TupleType):
        parts = [pool_values(e, pools, depth + 1) for e in t.elems]
        if all(parts):
            return [TupleValue([p[k % len(p)] for p in parts]) for k in range(max(len(p) for p in parts))]
    return []


def generate_chunk(checker, names_of, decls: list, out_path: str) -> None:
    """In a forked child: run each function of `decls` with its state
    parameters built by the factories, over the snippets and the recorded
    other arguments, and write the cases that come out to `out_path`."""
    with open(ARGS, encoding="utf-8") as fh:
        argsets = json.load(fh)
    pools = build_pools(checker, argsets)
    devnull = open(os.devnull, "w")
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    sandbox = os.path.join(STATE, "sandbox")   # where a stray relative path would land
    os.makedirs(sandbox, exist_ok=True)
    os.chdir(sandbox)
    sys.setrecursionlimit(100_000)
    interp = Interpreter(checker, out=devnull, err=devnull, argv=[ENTRY])
    impure = [False]
    orig_call = Interpreter._eval_call

    def call_hook(self, expr, env):
        # a generated call never does I/O: it stops before the primitive runs
        # (a function that makes directories or deletes files called with
        # pooled arguments must not touch anything)
        callee = expr.callee
        if isinstance(callee, ast.Name) and callee.ident in IMPURE:
            impure[0] = True
            raise _Impure()
        return orig_call(self, expr, env)

    Interpreter._eval_call = call_hook

    def stop(signum, frame_):
        raise _Timeout()

    signal.signal(signal.SIGALRM, stop)

    def timed(fn):
        signal.setitimer(signal.ITIMER_REAL, CALL_SECONDS)
        try:
            return fn()
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    built: dict[tuple, object] = {}

    def state(tname: str, choice):
        """(the factory's call as text in no module yet, the value) or None."""
        key = (tname, choice)
        if key not in built:
            mod, fname, how = FACTORIES[tname]
            q = _local_names(names_of, os.path.join(SELFHOST, mod)).get(fname)
            sig = checker.functions.get(q) if q else None
            args = [] if choice is None else [choice]
            try:
                value = timed(lambda: interp._call(sig.decl, list(args))) if sig else None
            except BaseException:
                value = None
            built[key] = (q, value)
        return built[key]

    out: dict[str, list] = {}
    for decl in decls:
        sig = checker.functions[decl.name]
        idx = state_params(checker, decl)
        tnames = {i: sig.params[i].name.split("$")[-1] for i in idx}
        pr = Printer(checker, names_of.get(os.path.realpath(decl.source_path), {}))
        others = [i for i in range(len(sig.params)) if i not in idx]
        if not others:
            sets = [[]]
        elif decl.name in argsets:
            sets = [pickle.loads(base64.b64decode(b)) for _, b in argsets[decl.name]]
        else:   # nobody recorded them: values of their types from the pools
            choices = [pool_values(sig.params[i], pools) for i in others]
            if not all(choices):
                continue
            sets = [[c[k % len(c)] for c in choices] for k in range(min(MAX_ARGSETS, max(map(len, choices))))]
        sets_used = [FACTORIES[t][2] for t in tnames.values() if isinstance(FACTORIES[t][2], str)]
        rounds = max((len(SNIPPETS[n]) for n in sets_used), default=1)
        cases: dict[str, None] = {}
        for k in range(rounds):
            texts, values, ok = {}, {}, True
            for i, t in tnames.items():
                how = FACTORIES[t][2]
                if isinstance(how, str):
                    snippet = SNIPPETS[how][k % len(SNIPPETS[how])]
                    choice = snippet
                else:
                    choice = how[0] if how else None
                q, value = state(t, choice)
                local = pr.names.get(q) if q else None
                if value is None or local is None:
                    ok = False
                    break
                if isinstance(how, str):
                    texts[i] = f'{local}("' + "".join(_escape_char(ord(c), '"') for c in snippet) + '")'
                elif how:
                    texts[i] = f"{local}({how[0]})"
                else:
                    texts[i] = f"{local}()"
                values[i] = value
            if not ok:
                continue
            for other_values in sets:
                args, arg_texts = [], []
                budget = MAX_GENERATED
                try:
                    k = 0
                    for i in range(len(sig.params)):
                        if i in values:
                            args.append(_copy(values[i]))
                            arg_texts.append(texts[i])
                        else:   # printed in this module's names
                            text = pr.show(other_values[k], sig.params[i], budget)
                            budget -= len(text) + 2
                            args.append(_copy(other_values[k]))
                            arg_texts.append(text)
                            k += 1
                except (Unprintable, KeyError, AttributeError, TypeError):
                    continue
                impure[0] = False
                try:
                    result = timed(lambda: interp._call(decl, args))
                except BaseException:
                    continue
                if impure[0]:
                    continue
                try:
                    res = pr.show(result, sig.ret, budget)
                except (Unprintable, KeyError, AttributeError, TypeError):
                    continue
                cases[json.dumps([arg_texts, res])] = None
        if cases:
            out[decl.name] = list(cases)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh)


def cmd_generate(jobs: int) -> None:
    t0 = time.time()
    checker, names_of = load()
    os.chdir(REPO)
    decls = list(eligible(checker).values())
    print(f"{len(decls)} functions without cases", flush=True)
    gen_dir = os.path.join(STATE, "generated")
    shutil.rmtree(gen_dir, ignore_errors=True)
    os.makedirs(gen_dir)
    chunks = [decls[i::jobs] for i in range(jobs)]
    pids = []
    for n, chunk in enumerate(chunks):
        pid = os.fork()
        if pid == 0:
            try:
                generate_chunk(checker, names_of, chunk, os.path.join(gen_dir, f"{n}.json"))
            finally:
                os._exit(0)
        pids.append(pid)
    for pid in pids:
        os.waitpid(pid, 0)
    merged: dict[str, list] = {}
    for f in sorted(os.listdir(gen_dir)):
        with open(os.path.join(gen_dir, f), encoding="utf-8") as fh:
            merged.update(json.load(fh))
    with open(GENERATED, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=0, sort_keys=True)
    print(f"{len(merged)} functions with generated cases, in {time.time() - t0:.0f} s")


# -- writing ------------------------------------------------------------------

def choose(cases: list[str], n: int = CASES_PER_FUNCTION) -> list[tuple[list[str], str]]:
    """Up to CASES_PER_FUNCTION cases spread over the sizes recorded (the
    smallest, the largest, then the middle), each with a result of its own
    where the calls allow."""
    parsed = sorted((json.loads(c) for c in cases), key=lambda c: (len(", ".join(c[0])) + len(c[1]), c))
    by_result: dict[str, list] = {}
    for c in parsed:
        by_result.setdefault(c[1], c)          # the smallest call per result
    pool = sorted(by_result.values(), key=lambda c: (len(", ".join(c[0])) + len(c[1]), c))
    if len(pool) < n:                         # too few results: other calls too
        pool += [c for c in parsed if c not in pool][:n - len(pool)]
        pool.sort(key=lambda c: (len(", ".join(c[0])) + len(c[1]), c))
    picks = []
    for i in (0, len(pool) - 1, len(pool) // 2):
        if pool and pool[i] not in picks and len(picks) < n:
            picks.append(pool[i])
    return [(a, r) for a, r in sorted(picks, key=lambda c: (len(", ".join(c[0])) + len(c[1]), c))]


def cmd_write() -> None:
    checker, _ = load()
    elig = {d.name: d for d in eligible(checker).values()}
    with open(RECORDS, encoding="utf-8") as fh:
        records = json.load(fh)
    generated = set()
    if os.path.exists(GENERATED):
        with open(GENERATED, encoding="utf-8") as fh:
            for name, cases in json.load(fh).items():
                records.setdefault(name, []).extend(cases)
                generated.add(name)
    inserts: dict[str, list[tuple[int, list[str]]]] = {}
    for name, cases in records.items():
        decl = elig.get(name)
        if decl is None:
            continue
        n = GENERATED_PER_FUNCTION if name in generated and state_params(checker, decl) else CASES_PER_FUNCTION
        lines = [f"#test({', '.join(args)})[{res}]" for args, res in choose(cases, n)]
        inserts.setdefault(os.path.realpath(decl.source_path), []).append((decl.line, lines))
    total = 0
    for path, items in sorted(inserts.items()):
        with open(path, encoding="utf-8") as fh:
            src = fh.read().split("\n")
        for line, cases in sorted(items, reverse=True):
            indent = re.match(r"\s*", src[line - 1]).group(0)
            src[line - 1:line - 1] = [indent + c for c in cases]
            total += len(cases)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(src))
        print(f"  {os.path.relpath(path, REPO)}: {len(items)} functions")
    print(f"{total} cases written")


# -- validating ---------------------------------------------------------------

_POS = re.compile(r"^\s*--> (.*):(\d+):(\d+)")
_FAIL = re.compile(r"^FAIL  (\S+) #(\d+)")


def _case_lines(path: str) -> dict[tuple[str, int], int]:
    """(name as the runner prints it, case number) -> line of the case."""
    from myla.lexer import tokenize
    from myla.parser import parse
    with open(path, encoding="utf-8") as fh:
        prog = parse(tokenize(fh.read()))
    out = {}

    def add(name, decl):
        k = 0
        for a in decl.attributes:
            if a.name == "test":
                k += 1
                out[(name, k)] = a.line
    for d in prog.decls:
        if isinstance(d, ast.FunDecl):
            add(d.name, d)
        elif isinstance(d, ast.ImplDecl) and isinstance(d.target, ast.TypeRef):
            for m in d.methods:
                add(f"{d.target.name}.{m.name}", m)
    return out


def _generated(line: str) -> bool:
    return line.lstrip().startswith("#test(")


def _drop(path: str, lines: set[int]) -> int:
    with open(path, encoding="utf-8") as fh:
        src = fh.read().split("\n")
    dropped = 0
    for ln in sorted(lines, reverse=True):
        if 1 <= ln <= len(src) and _generated(src[ln - 1]):
            del src[ln - 1]
            dropped += 1
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(src))
    return dropped


def _runners(path: str):
    py = [sys.executable, os.path.join(REPO, "myla.py"), "test", path]
    my = [os.path.join(REPO, "build", "myla"), "test", path, "--stdlib", STDLIB]
    return [py, my]


def cmd_validate(paths: list[str]) -> None:
    if not paths:
        paths = sorted(os.path.join(SELFHOST, f) for f in os.listdir(SELFHOST) if f.endswith(".my"))
    for path in paths:
        removed = 0
        for _ in range(60):
            bad: set[int] = set()
            for cmd in _runners(path):
                r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
                if r.returncode == 0:
                    continue
                cases = _case_lines(path)
                for ln in (r.stdout + r.stderr).split("\n"):
                    m = _POS.match(ln)
                    if m and os.path.realpath(m.group(1)) == os.path.realpath(path):
                        bad.add(int(m.group(2)))
                    m = _FAIL.match(ln)
                    if m and (m.group(1), int(m.group(2))) in cases:
                        bad.add(cases[(m.group(1), int(m.group(2)))])
                if bad:
                    break
                print(f"  {os.path.relpath(path, REPO)}: {cmd[1] if 'myla.py' in cmd[1] else 'build/myla'} "
                      f"fails without a case to blame:\n{(r.stdout + r.stderr)[-800:]}")
                return
            if not bad:
                break
            n = _drop(path, bad)
            if n == 0:
                print(f"  {os.path.relpath(path, REPO)}: errors at lines {sorted(bad)[:8]} are not generated cases")
                return
            removed += n
        print(f"  {os.path.relpath(path, REPO)}: ok, {removed} cases removed", flush=True)


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "record":
        cmd_record(int(os.environ.get("JOBS", os.cpu_count() or 2)))
    elif cmd == "generate":
        cmd_generate(int(os.environ.get("JOBS", os.cpu_count() or 2)))
    elif cmd == "merge":
        merge_parts()
    elif cmd == "write":
        cmd_write()
    elif cmd == "validate":
        cmd_validate(sys.argv[2:])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
