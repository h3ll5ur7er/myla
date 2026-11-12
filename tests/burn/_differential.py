"""Differential runs of generated programs (MYLA-555): the review's
generators as burn tests.

A generator makes a program of numbered cases. `driver` puts them behind a
`main` that runs the cases from the index its first argument names, and
prints `@@end <i>` after case `i`. `run_cases` runs such a program on one
runner and gives each case's output: when a case stops the program (a
runtime error, a signal, a trap, a time limit), what it printed and how it
ended are its result, and the program is started again at the next case, so
one failing case doesn't hide the others (the review's `harness.py`).

`compare` runs a program on several runners at once and holds the cases to
one answer: every runner prints the same, and `valid` (a test's own
condition, such as "no case reported a bad copy") holds. A case that fails
today because of a bug another task fixes is in the test's `known` map, with
the task: such a case must still fail (once fixed, the task removes its
entry), and every other case must pass.

The size: each test runs a sample of its generator's cases, drawn from a
fixed seed and always holding the known failures, small enough for the
suite. `MYLA_GENERATED=full` runs every case, and `MYLA_GENERATED_SEED`
draws another sample.

The runners: the self-hosted interpreter (`myla run`), the native build and
the `--checked` one. With MYLA_TEST_TARGET set the native builds are for that
target (`_native.py`) and run under qemu-aarch64 or Node.
"""
from __future__ import annotations

import concurrent.futures
import os
import random
import re
import resource
import subprocess

from ._native import TEST_TARGET, Program, native_build, run_argv
from ._tools import STDLIB_ROOT, selfhost_tool

FULL = os.environ.get("MYLA_GENERATED", "") == "full"
SEED = int(os.environ.get("MYLA_GENERATED_SEED", "555"))

# a case's partial output and how it ended, after the case's marker went
# missing; the source excerpt of a runtime error is left out (its lines
# start with a line number and `|`), as positions are compared on its first
# line
_EXCERPT = re.compile(r"^ *[0-9]* \|( |$)")
_MARK = re.compile(r"@@end ([0-9]+)\n")
# a case that takes more memory than this fails, not the machine (the
# review's harness gave each run 1 GiB of address space); only for programs
# run on this machine, as qemu and Node reserve more
_ADDRESS_SPACE = 1 << 30

# the cases of one part of `main` (a function each, so no function is huge)
_PART = 64


def sample(names: list[str], n: int, salt: str, keep=()) -> list[str]:
    """`n` of `names` drawn from the seed and `salt`, in their order, with
    those of `keep` among them; all of them with MYLA_GENERATED=full."""
    if FULL or n >= len(names):
        return list(names)
    rng = random.Random(f"{SEED}:{salt}")
    chosen = set(rng.sample(names, n)) | (set(keep) & set(names))
    return [x for x in names if x in chosen]


def driver(prelude: str, cases: list[tuple[str, str]], is_async: bool = False) -> str:
    """A program of `prelude` and the cases, each (its declarations, the
    statements that run it), whose `main` runs them from `args()[1]` on."""
    out = [prelude, "import std.process as gen_process", "import std.num as gen_num", "import std.io as gen_io"]
    fun = "async fun" if is_async else "fun"
    call = "await " if is_async else ""
    for decls, _ in cases:
        out.append(decls)
    parts = (len(cases) + _PART - 1) // _PART
    for p in range(parts):
        out.append(f"{fun} gen_part_{p}(start: int) {{")
        for i in range(p * _PART, min(len(cases), (p + 1) * _PART)):
            out.append(f"    if start <= {i} {{")
            out.extend("        " + line for line in cases[i][1].split("\n"))
            out.append(f'        gen_io.println("@@end {i}")')
            out.append("    }")
        out.append("}")
    out.append("#main" if is_async else "")
    out.append(f"{fun} main() {{")
    out.append("    let a = gen_process.args()")
    out.append("    var start = 0")
    out.append("    if a.len() > 1 { start = gen_num.parse_int(a[1]).unwrap_or(0) as int }")
    for p in range(parts):
        out.append(f"    if start < {(p + 1) * _PART} {{ {call}gen_part_{p}(start) }}")
    out.append("}")
    return "\n".join(out) + "\n"


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if not TEST_TARGET:
        resource.setrlimit(resource.RLIMIT_AS, (_ADDRESS_SPACE, _ADDRESS_SPACE))


def ending(code: int | None, err: str) -> str:
    """How a run ended, as a case's result: its exit status or signal, and
    what it wrote to stderr without the source excerpts."""
    if code is None:
        how = "timed out"
    elif code < 0:
        how = f"signal {-code}"
    else:
        how = f"exit {code}"
    text = "\n".join(line for line in err.splitlines() if not _EXCERPT.match(line))
    return f"!! {how}: {text}"


def run_cases(argv: list[str], exe: str | None, count: int, env: dict | None = None,
              timeout: float = 120) -> list[str]:
    """The output of each of the `count` cases of a `driver` program run as
    `argv` (the start index appended), restarted after a case that ends it.
    A case that runs `timeout` seconds from its own start fails with `timed
    out`."""
    results: list[str] = []
    while len(results) < count:
        start = len(results)
        try:
            proc = subprocess.run(argv + [str(start)], executable=exe, capture_output=True, timeout=timeout,
                                  env=env, preexec_fn=_limits)
            out, err, code = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as e:
            out, err, code = e.stdout or b"", e.stderr or b"", None
        text = out.decode("utf-8", "replace")
        pos = 0
        for m in _MARK.finditer(text):
            if int(m.group(1)) != len(results):
                raise AssertionError(f"case {len(results)} expected, the program ended case {m.group(1)}")
            results.append(text[pos:m.start()])
            pos = m.end()
        if code is None and len(results) > start:
            # out of time after some cases: the one it was in starts a run of
            # its own, so each case has the whole time limit
            continue
        if len(results) < count and (code != 0 or len(results) == start):
            # the case that ended the program: what it printed, and how
            results.append(text[pos:] + ending(code, err.decode("utf-8", "replace")))
        elif len(results) < count:
            raise AssertionError(f"the program ended after case {len(results) - 1} of {count}, exit 0")
    return results


class Runner:
    """A way to run a driver program: `kind` is `interpreted`, `native` or
    `checked`; `env` extra environment variables (MYLA_THREADS)."""

    def __init__(self, name: str, kind: str, env: dict | None = None):
        self.name, self.kind, self.env = name, kind, env


INTERPRETED = Runner("interpreted", "interpreted")
NATIVE = Runner("native", "native")
CHECKED = Runner("checked", "checked")
THREE = [INTERPRETED, NATIVE, CHECKED]


def run_all(path: str, count: int, runners: list[Runner], timeout: float = 120) -> dict[str, list[str]]:
    """Each runner's results of the driver program `path`, the runners run
    at once (the builds first)."""
    binaries = {}
    for kind in {r.kind for r in runners} - {"interpreted"}:
        binary = f"{path[:-3]}.{kind}"
        native_build(Program(path), binary, checked=kind == "checked")
        binaries[kind] = binary

    def one(r: Runner) -> list[str]:
        env = dict(os.environ, **r.env) if r.env else None
        if r.kind == "interpreted":
            argv, exe = [selfhost_tool("main"), "run", path, "--stdlib", STDLIB_ROOT], None
        else:
            argv, exe = run_argv(binaries[r.kind], "prog")
        return run_cases(argv, exe, count, env, timeout)

    workers = max(1, min(len(runners), os.cpu_count() or 1))
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        got = dict(zip([r.name for r in runners], pool.map(one, runners)))
    return got


def verdicts(names: list[str], results: dict[str, list[str]], valid=None, compared=None) -> dict[str, str]:
    """The cases that fail, each with why: the runners disagree (those of
    `compared(name, outputs)` if given), or `valid(name, outputs)` gives a
    problem (None when the case is good)."""
    bad = {}
    for i, name in enumerate(names):
        outs = {r: results[r][i] for r in results}
        if compared is not None:
            outs = {r: outs[r] for r in compared(name, outs)}
        if len(set(outs.values())) > 1:
            bad[name] = "the runners disagree"
        elif valid is not None:
            problem = valid(name, outs)
            if problem:
                bad[name] = problem
    return bad


def report(names: list[str], results: dict[str, list[str]], failing: dict[str, str], cases: list[str],
           limit: int = 6, width: int = 400) -> str:
    """The first `limit` of `cases` with each runner's output."""
    lines = []
    for name in cases[:limit]:
        i = names.index(name)
        lines.append(f"[{name}] {failing.get(name, 'passes')}")
        for r, outs in results.items():
            text = outs[i].replace("\n", " | ")
            lines.append(f"    {r:12} {text[:width]}{'…' if len(text) > width else ''}")
    if len(cases) > limit:
        lines.append(f"… and {len(cases) - limit} more: {' '.join(cases[limit:limit + 60])}")
    return "\n".join(lines)


def known_here(known: dict) -> dict[str, str]:
    """The known failures on this target: an entry's value is its task, or a
    map from target ("" this machine's, "aarch64-linux", "wasm32-wasi", "*"
    every target) to the task."""
    out = {}
    for name, task in known.items():
        if isinstance(task, str):
            out[name] = task
        elif TEST_TARGET in task or "*" in task:
            out[name] = task.get(TEST_TARGET, task.get("*"))
    return out


def check(test, names: list[str], results: dict[str, list[str]], known: dict, valid=None, compared=None,
          may_pass=()) -> None:
    """Fails `test` on a case that fails without being known, or that is
    known and passes (its task fixed it: remove its entry), unless it is
    one of `may_pass` (a case that fails only when it takes too long)."""
    known = known_here(known)
    failing = verdicts(names, results, valid, compared)
    new = [n for n in names if n in failing and n not in known]
    fixed = [n for n in names if n in known and n not in failing and n not in may_pass]
    msgs = []
    if new:
        msgs.append(f"{len(new)} of {len(names)} cases fail:\n" + report(names, results, failing, new))
    if fixed:
        msgs.append(f"{len(fixed)} known failures pass now; remove them from the test's known list: "
                    + " ".join(f"{n} ({known[n]})" for n in fixed))
    if msgs:
        test.fail("\n".join(msgs))
