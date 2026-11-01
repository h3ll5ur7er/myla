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

import json
import math
import os
import re
import signal
import struct
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

from myla import ast, loader                              # noqa: E402
from myla.interpreter import (EnumValue, Interpreter, ListValue, MapValue,  # noqa: E402
                              StructValue, TupleValue, _Env)
from myla.types import (BoolType, CharType, EnumType, FloatType, IntType,  # noqa: E402
                        ListType, MapType, StrType, StructType, TupleType,
                        TypeParam, check)

SELFHOST = os.path.join(REPO, "selfhost")
ENTRY = os.path.join(SELFHOST, "main.my")
STDLIB = os.path.join(REPO, "src", "myla")
STATE = os.path.join(REPO, "build", "harvest")
RECORDS = os.path.join(STATE, "records.json")

MAX_CASE = 220          # characters of one case's arguments and result together
MAX_DISTINCT = 40       # distinct calls kept per function while recording
CASES_PER_FUNCTION = 3
WORKLOAD_SECONDS = 240

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


def workloads() -> list[list[str]]:
    examples = sorted(os.path.join("examples", f) for f in os.listdir(os.path.join(REPO, "examples"))
                      if f.endswith(".my"))
    errors = sorted(os.path.join("examples", "errors", f)
                    for f in os.listdir(os.path.join(REPO, "examples", "errors")) if f.endswith(".my"))
    out = []
    for ex in examples:
        out.append(["check", ex])
        out.append(["build", ex, "-o", os.path.join(STATE, "bin", os.path.basename(ex)[:-3])])
        out.append(["test", ex])
    for ex in examples:
        out.append(["run", ex])
    for err in errors:
        out.append(["check", err])
    return out


# -- recording ----------------------------------------------------------------

def record_one(checker, names_of, elig, argv: list[str], out_path: str) -> None:
    """Run the CLI on `argv` with the hooks (in a forked child) and write the
    calls kept to `out_path`."""
    printers = {}
    calls: dict[str, dict[str, None]] = {}
    stack: list[list] = []

    def printer(decl):
        path = os.path.realpath(decl.source_path)
        if path not in printers:
            printers[path] = Printer(checker, names_of.get(path, {}))
        return printers[path]

    orig_run = Interpreter._run
    orig_call = Interpreter._eval_call

    def run_hook(self, body, frame, path, is_block=True):
        decl = elig.get(id(body))
        if decl is None or len(calls.get(decl.name, ())) >= MAX_DISTINCT:
            return orig_run(self, body, frame, path, is_block)
        sig = checker.functions[decl.name]
        pr = printer(decl)
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
        raise TimeoutError()

    signal.signal(signal.SIGALRM, stop)
    signal.alarm(WORKLOAD_SECONDS)
    devnull = open(os.devnull, "w")
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)   # a program that reads stdin reads nothing
    sys.setrecursionlimit(100_000)
    try:
        Interpreter(checker, out=devnull, err=devnull, argv=[ENTRY, *argv]).run()
    except BaseException:   # a timeout, an error of the program: keep what was seen
        pass
    signal.alarm(0)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({k: list(v) for k, v in calls.items()}, fh)


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
    todo = [(i, w) for i, w in enumerate(workloads()) if only.search(" ".join(w))
            and not os.path.exists(os.path.join(parts, f"{i:04d}.json"))]
    print(f"{len(todo)} workloads to run", flush=True)
    running: dict[int, tuple] = {}
    while todo or running:
        while todo and len(running) < jobs:
            i, argv = todo.pop(0)
            part = os.path.join(STATE, "parts", f"{i:04d}.json")
            pid = os.fork()
            if pid == 0:
                try:
                    record_one(checker, names_of, elig, argv, part)
                finally:
                    os._exit(0)
            running[pid] = (i, argv, time.time())
        pid, _ = os.wait()
        i, argv, started = running.pop(pid)
        print(f"  [{i}] {' '.join(argv[:2])}: {time.time() - started:.0f} s", flush=True)
    merge_parts()
    print(f"done in {time.time() - t0:.0f} s")


def merge_parts() -> None:
    merged: dict[str, list] = {}
    for part in sorted(os.listdir(os.path.join(STATE, "parts"))):
        with open(os.path.join(STATE, "parts", part), encoding="utf-8") as fh:
            for name, cases in json.load(fh).items():
                seen = merged.setdefault(name, [])
                for c in cases:
                    if c not in seen:
                        seen.append(c)
    with open(RECORDS, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=0, sort_keys=True)
    print(f"{len(merged)} functions with recorded calls")


# -- writing ------------------------------------------------------------------

def choose(cases: list[str]) -> list[tuple[list[str], str]]:
    """Up to CASES_PER_FUNCTION cases spread over the sizes recorded (the
    smallest, the largest, then the middle), each with a result of its own
    where the calls allow."""
    parsed = sorted((json.loads(c) for c in cases), key=lambda c: (len(", ".join(c[0])) + len(c[1]), c))
    by_result: dict[str, list] = {}
    for c in parsed:
        by_result.setdefault(c[1], c)          # the smallest call per result
    pool = sorted(by_result.values(), key=lambda c: (len(", ".join(c[0])) + len(c[1]), c))
    if len(pool) < CASES_PER_FUNCTION:        # too few results: other calls too
        pool += [c for c in parsed if c not in pool][:CASES_PER_FUNCTION - len(pool)]
        pool.sort(key=lambda c: (len(", ".join(c[0])) + len(c[1]), c))
    picks = []
    for i in (0, len(pool) - 1, len(pool) // 2):
        if pool and pool[i] not in picks and len(picks) < CASES_PER_FUNCTION:
            picks.append(pool[i])
    return [(a, r) for a, r in sorted(picks, key=lambda c: (len(", ".join(c[0])) + len(c[1]), c))]


def cmd_write() -> None:
    checker, _ = load()
    elig = {d.name: d for d in eligible(checker).values()}
    with open(RECORDS, encoding="utf-8") as fh:
        records = json.load(fh)
    inserts: dict[str, list[tuple[int, list[str]]]] = {}
    for name, cases in records.items():
        decl = elig.get(name)
        if decl is None:
            continue
        lines = [f"#test({', '.join(args)})[{res}]" for args, res in choose(cases)]
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
