"""Burn test: `std.regex` (MYLA-335, MYLA-421) against Go's `regexp` and
Python's `re`, a differential job from the review of 2026-11-09.

Patterns are generated at random from the syntax both sides have: literals,
`.`, classes, Perl classes, the assertions (`\\b`, `\\B`, `^`, `$`, `\\A`,
`\\z`, multi-line `^` and `$`), groups with and without a capture, flag
groups, alternation (with empty alternatives) and every repetition, greedy
and lazy, nested up to three deep. The texts are drawn from small alphabets
so that patterns match, mostly 96 bytes or longer, where a search goes
through the lazy DFAs, and some shorter, where the Pike VM does it alone.

A Myla driver answers each case as the oracle does: whether it matches, the
leftmost-first match (`find`), every match (`find_all`) and the groups of the
first (`captures`); the answers must be the same.

- Go's `regexp` has the same semantics as `std.regex` (leftmost-first, as
  RE2's Pike VM), so it checks the whole syntax, but for a literal `A`:
  go1.24's parser merges a case-sensitive `A` with a case-folded `a` that
  starts another alternative, and finds `A|(?i:a)c` in `acA` at 2-3, where
  Python and `std.regex` find 0-2. The test skips without `go`.
- Python's `re` backtracks: it agrees only where no repetition can repeat
  an empty match, so its patterns repeat only what can't be empty, and `$`
  and `\\z` are written in its spelling. Backtracking takes exponential
  time on some of them, so a case Python doesn't answer within 20 ms is left
  out. It is always there to run.

The big corpora run on the self-hosted native build, a small one on the
self-hosted interpreter.
"""
from __future__ import annotations

import os
import random
import re
import shutil
import signal
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON
from ._tools import STDLIB_ROOT, selfhost_tool

DRIVER = """import std.regex as regex
import std.encoding as encoding
import std.io as io
import std.process as process

fun unhex(s: str) -> str {
    var sb = StringBuilder()
    match encoding.hex_decode(s) {
        Ok(b) => { for x in b { sb.append_byte(x) } }
        Err(_) => { process.exit(2) }
    }
    return sb.build()
}

// A line `m <pattern> <text>`, both in hex, answered as the oracle does:
// `<is_match> F<find> A<find_all> C<captures> G<groups>`.
fun answer(line: str) -> str {
    let f = line.split(" ")
    let re = match regex.compile(unhex(f[1])) {
        Ok(r) => r
        Err(_) => {
            return "ERR"
        }
    }
    let text = unhex(f[2])
    var sb = StringBuilder()
    sb.append(if re.is_match(text) { "true F" } else { "false F" })
    match re.find(text) {
        Some(m) => sb.append(f"{m.start}-{m.end}")
        None => sb.append("none")
    }
    sb.append(" A")
    for m in re.find_all(text) {
        sb.append(f"{m.start}-{m.end};")
    }
    sb.append(" C")
    match re.captures(text) {
        Some(c) => {
            for i in 0..c.len() {
                match c.get(i) {
                    Some(m) => sb.append(f"{m.start}-{m.end},")
                    None => sb.append("x,")
                }
            }
        }
        None => sb.append("none")
    }
    sb.append(f" G{re.group_count()}")
    return sb.build()
}

fun main() {
    var input = io.stdin()
    let all = input.read_to_end().unwrap_or("")
    var out = StringBuilder()
    for line in all.split("\\n") {
        if line.len() == 0 { continue }
        out.append(answer(line))
        out.append("\\n")
    }
    match io.write(1, out.build()) {
        Ok(()) => {}
        Err(_) => { process.exit(3) }
    }
}
"""

# The review's oracle (repro/std/regex-oracle/gooracle), the `m` lines only.
GO_ORACLE = """package main

import (
	"bufio"
	"encoding/hex"
	"fmt"
	"os"
	"regexp"
	"strings"
)

func main() {
	sc := bufio.NewScanner(os.Stdin)
	sc.Buffer(make([]byte, 1<<20), 1<<26)
	w := bufio.NewWriter(os.Stdout)
	defer w.Flush()
	for sc.Scan() {
		f := strings.Split(sc.Text(), " ")
		pat, _ := hex.DecodeString(f[1])
		re, err := regexp.Compile(string(pat))
		if err != nil {
			fmt.Fprintf(w, "ERR %q\\n", err.Error())
			continue
		}
		text, _ := hex.DecodeString(f[2])
		var sb strings.Builder
		fmt.Fprintf(&sb, "%v F", re.Match(text))
		loc := re.FindIndex(text)
		if loc == nil {
			sb.WriteString("none")
		} else {
			fmt.Fprintf(&sb, "%d-%d", loc[0], loc[1])
		}
		sb.WriteString(" A")
		for _, m := range re.FindAllIndex(text, -1) {
			fmt.Fprintf(&sb, "%d-%d;", m[0], m[1])
		}
		sb.WriteString(" C")
		c := re.FindSubmatchIndex(text)
		if c == nil {
			sb.WriteString("none")
		} else {
			for i := 0; i < len(c); i += 2 {
				if c[i] < 0 {
					sb.WriteString("x,")
				} else {
					fmt.Fprintf(&sb, "%d-%d,", c[i], c[i+1])
				}
			}
		}
		fmt.Fprintf(&sb, " G%d", re.NumSubexp())
		fmt.Fprintln(w, sb.String())
	}
}
"""

ASSERTIONS = ["\\b", "\\B", "^", "$", "\\A", "\\z", "(?m:^)", "(?m:$)"]
REPEATS = ["*", "+", "?", "*?", "+?", "??", "{2}", "{0,2}", "{1,}", "{1,3}?", "{2,}?", "{0}"]
# repetitions that can't make a body that can't be empty match empty
NONEMPTY_REPEATS = ["+", "+?", "{2}", "{1,}", "{1,3}?", "{2,}?"]
ALPHABETS = ["ab", "abc", "abc1 _A-", "ab ", "aA1", "ab\n", "a \n-"]


class Generator:
    """The review's generator (repro/std/regex-oracle/gen2.py). With
    `python`, only what Python's `re` agrees on: no repetition of what can
    be empty and no `(?U:`; each piece is made in Go's spelling and in
    Python's, which spells `\\z` as `\\Z` and has no bare `$` (a bare `$` of
    Python's matches before a final newline too)."""

    def __init__(self, rng: random.Random, python: bool) -> None:
        self.rng = rng
        self.python = python

    # each returns (Go's spelling, Python's spelling, whether it can be empty)
    def atom(self, d: int) -> tuple[str, str, bool]:
        r = self.rng.random()
        if r < 0.30:
            c = self.rng.choice(["a", "a", "b", "b", "c", "1", " ", "_", "A", "-"])
            if c == "A" and not self.python:
                c = "c"
            return c, re.escape(c), False
        if r < 0.36:
            return ".", ".", False
        if r < 0.44:
            c = self.rng.choice(["[ab]", "[^a]", "[a-c]", "[^ab]", "\\d", "\\w", "\\s", "\\D", "\\W", "\\S"])
            return c, c, False
        if r < 0.62:
            a = self.rng.choice(ASSERTIONS)
            if self.python and a == "$":
                a = "\\z"
            return a, a.replace("\\z", "\\Z"), True
        if d >= 3:
            return "a", "a", False
        g, p, empty = self.alt(d + 1)
        k = self.rng.random()
        if k < 0.5:
            return "(" + g + ")", "(" + p + ")", empty
        if k < 0.8:
            return "(?:" + g + ")", "(?:" + p + ")", empty
        flags = ["(?i:", "(?s:"] if self.python else ["(?i:", "(?s:", "(?U:", "(?m:"]
        f = self.rng.choice(flags)
        return f + g + ")", f + p + ")", empty

    def piece(self, d: int) -> tuple[str, str, bool]:
        g, p, empty = self.atom(d)
        if self.rng.random() < 0.5 or g in ASSERTIONS:
            return g, p, empty
        if self.python:
            if empty:
                return g, p, empty
            q = self.rng.choice(NONEMPTY_REPEATS)
            return g + q, p + q, False
        q = self.rng.choice(REPEATS)
        return g + q, p + q, empty or q[0] in "*?" or q.startswith("{0")

    def seq(self, d: int) -> tuple[str, str, bool]:
        parts = [self.piece(d) for _ in range(self.rng.choice([1, 1, 2, 2, 3]))]
        return "".join(x[0] for x in parts), "".join(x[1] for x in parts), all(x[2] for x in parts)

    def alt(self, d: int) -> tuple[str, str, bool]:
        k = self.rng.choice([1, 1, 1, 2, 3])
        parts = [self.seq(d) for _ in range(k)]
        if k > 1 and self.rng.random() < 0.15:
            parts.append(("", "", True))
        return "|".join(x[0] for x in parts), "|".join(x[1] for x in parts), any(x[2] for x in parts)

    def case(self, long: bool) -> tuple[str, str, bytes]:
        g, p, _ = self.alt(0)
        alphabet = self.rng.choice(ALPHABETS)
        if long:
            n = self.rng.choice([96, 97, 100, 120, 160, 300])
        else:
            n = self.rng.choice([1, 2, 3, 5, 8, 20, 50, 95, 96, 97, 120])
        return g, p, "".join(self.rng.choice(alphabet) for _ in range(n)).encode()


def corpus(seed: int, n: int, long_share: float, python: bool) -> list[tuple[str, str, bytes]]:
    rng = random.Random(seed)
    gen = Generator(rng, python)
    return [gen.case(rng.random() < long_share) for _ in range(n)]


def line(pattern: str, text: bytes) -> str:
    return f"m {pattern.encode().hex()} {text.hex()}"


class TooSlow(Exception):
    pass


def _too_slow(signum, frame) -> None:
    raise TooSlow()


def python_answers(cases: list[tuple[str, bytes]]) -> list[str | None]:
    """`python_answer` of each case, None for one that takes more than 20 ms
    (`re` checks for signals while it matches)."""
    old = signal.signal(signal.SIGALRM, _too_slow)
    out: list[str | None] = []
    try:
        for pattern, text in cases:
            signal.setitimer(signal.ITIMER_REAL, 0.02)
            try:
                out.append(python_answer(pattern, text))
            except TooSlow:
                out.append(None)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
    finally:
        signal.signal(signal.SIGALRM, old)
    return out


def python_answer(pattern: str, text: bytes) -> str:
    """What the Go oracle prints, from Python's `re` on bytes (ASCII
    classes), with Go's rules for `find_all`: after an empty match the
    search goes on a byte later, and an empty match right after a match
    doesn't count."""
    try:
        rx = re.compile(pattern.encode())
    except re.error:
        return "ERR"
    first = rx.search(text)
    out = [("true" if first else "false") + " F" + (f"{first.start()}-{first.end()}" if first else "none"), " A"]
    pos, prev_end = 0, -1
    while pos <= len(text):
        m = rx.search(text, pos)
        if m is None:
            break
        a, b = m.span()
        if a == b:
            pos = a + 1
            if a == prev_end:
                prev_end = b
                continue
        else:
            pos = b
        prev_end = b
        out.append(f"{a}-{b};")
    out.append(" C")
    if first is None:
        out.append("none")
    else:
        for i in range(rx.groups + 1):
            a, b = first.span(i)
            out.append("x," if a < 0 else f"{a}-{b},")
    out.append(f" G{rx.groups}")
    return "".join(out)


class RegexDifferentialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp()
        cls.path = os.path.join(cls.tmp, "driver.my")
        with open(cls.path, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        cls.native = None
        if CAN_BUILD_NATIVE:
            asm = subprocess.run([selfhost_tool("gen_main"), cls.path, STDLIB_ROOT], capture_output=True, text=True,
                                 check=True)
            exe = os.path.join(cls.tmp, "driver")
            with open(exe + ".s", "w", encoding="utf-8") as fh:
                fh.write(asm.stdout)
            subprocess.run(["as", "--64", "-o", exe + ".o", exe + ".s"], check=True)
            subprocess.run(["ld", "-o", exe, exe + ".o"], check=True)
            cls.native = exe
            # the same driver built checked, where an integer overflow is an error (D184, MYLA-550)
            cls.checked = os.path.join(cls.tmp, "driver-checked")
            subprocess.run([selfhost_tool("main"), "build", cls.path, "-o", cls.checked, "--stdlib", STDLIB_ROOT,
                            "--checked"], capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def myla(self, native: bool, lines: list[str]) -> list[str]:
        if native:
            argv = [self.native]
        else:
            argv = [selfhost_tool("main"), "run", self.path, "--stdlib", STDLIB_ROOT]
        proc = subprocess.run(argv, input="\n".join(lines) + "\n", capture_output=True, text=True, timeout=900)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.splitlines()
        self.assertEqual(len(out), len(lines))
        return out

    def go(self, lines: list[str]) -> list[str]:
        src = os.path.join(self.tmp, "gooracle")
        exe = os.path.join(self.tmp, "gooracle-bin")
        if not os.path.exists(exe):
            os.makedirs(src, exist_ok=True)
            with open(os.path.join(src, "go.mod"), "w", encoding="utf-8") as fh:
                fh.write("module gooracle\n\ngo 1.21\n")
            with open(os.path.join(src, "main.go"), "w", encoding="utf-8") as fh:
                fh.write(GO_ORACLE)
            env = dict(os.environ, GOTOOLCHAIN="local", GOFLAGS="-mod=mod")
            subprocess.run(["go", "build", "-o", exe, "."], cwd=src, env=env, check=True, capture_output=True)
        proc = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, check=True,
                              timeout=600)
        return proc.stdout.splitlines()

    def compare(self, cases: list[tuple[str, bytes]], want: list[str], got: list[str]) -> None:
        self.assertEqual(len(want), len(got))
        compared, bad = 0, []
        for (pattern, text), w, g in zip(cases, want, got):
            if w.startswith("ERR") or g == "ERR":
                # both refuse the pattern, or the syntaxes differ: generated
                # patterns are of the syntax both have
                self.assertEqual(w.startswith("ERR"), g == "ERR", f"{pattern!r}: {w} / {g}")
                continue
            compared += 1
            if w != g:
                bad.append(f"{pattern!r} on {text!r} ({len(text)} bytes)\n  oracle: {w}\n  std.regex: {g}")
        self.assertGreater(compared, len(cases) * 9 // 10)
        self.assertEqual(bad[:5], [], f"{len(bad)} of {compared} cases disagree")

    def against_go(self, native: bool, seed: int, n: int) -> None:
        made = corpus(seed, n, 0.75, python=False)
        lines = [line(g, t) for g, _, t in made]
        self.compare([(g, t) for g, _, t in made], self.go(lines), self.myla(native, lines))

    def against_python(self, native: bool, seed: int, n: int) -> None:
        made = corpus(seed, n, 0.75, python=True)
        answered = [(g, t, w) for (g, _, t), w in zip(made, python_answers([(p, t) for _, p, t in made]))
                    if w is not None]
        self.assertGreater(len(answered), n * 9 // 10)
        got = self.myla(native, [line(g, t) for g, t, _ in answered])
        self.compare([(g, t) for g, t, _ in answered], [w for _, _, w in answered], got)

    @unittest.skipUnless(shutil.which("go"), "Go isn't installed")
    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_go_natively(self) -> None:
        self.against_go(True, 4210, 40_000)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_python_natively(self) -> None:
        self.against_python(True, 4211, 10_000)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_checked_natively(self) -> None:
        # the plain and the checked build answer the same, counted
        # repetitions such as `a{99999999999}` included
        made = corpus(4214, 10_000, 0.75, python=True)
        lines = [line(g, t) for g, _, t in made]
        lines += [line(f"a{{{n}}}", b"aaa") for n in ("2147483647", "2147483648", "4294967296", "99999999999999999999")]
        lines += [line(f"a{{1,{n}}}", b"aaa") for n in ("2147483647", "2147483648", "99999999999999999999")]
        plain = self.myla(True, lines)
        proc = subprocess.run([self.checked], input="\n".join(lines) + "\n", capture_output=True, text=True,
                              timeout=900)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), plain, "the plain and the checked build differ")

    @unittest.skipUnless(shutil.which("go"), "Go isn't installed")
    def test_go_interpreted(self) -> None:
        self.against_go(False, 4212, 100)

    def test_python_interpreted(self) -> None:
        self.against_python(False, 4213, 60)


if __name__ == "__main__":
    unittest.main()
