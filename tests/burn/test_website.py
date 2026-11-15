"""Burn test: what the website runs is right (D208, MYLA-159).

- Every exercise of the course (learn/, MYLA-634) is not solved as given and
  is solved by its solution, by the rules the site's Check button applies: an
  exercise with `// expect:` lines prints exactly them, one without passes
  the starter's #test cases and its `// hidden:` ones in place of the
  learner's (or, with `// own-tests: N`, the learner's, at least N, and the
  hidden ones); ten seconds is the limit, as in the browser. The transform
  mirrors website/src/app/core/exercise-check.ts.
- The course's files are well formed: each chapter has a title, each
  exercise a title and positive XP and a solution, each chapter one boss.
- The landing page's samples (website/src/app/pages/home/samples) print their
  `// output:` trailers.
- tools/doc (MYLA-632) documents every module of the standard library.

The website's own tests (its content pipeline, the gamification, the editor's
Myla mode) run with `npm test` in website/, in CI's website job."""
import json
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._tools import STDLIB_ROOT, myla_tool, selfhost_tool

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEARN = os.path.join(_REPO, "learn")
SAMPLES = os.path.join(_REPO, "website", "src", "app", "pages", "home", "samples")
LIMIT = 10  # seconds, as the site's editor


def exercises() -> list[str]:
    out = []
    for ch in sorted(os.listdir(LEARN)):
        d = os.path.join(LEARN, ch)
        if os.path.isdir(d) and re.match(r"^\d+-", ch):
            out += [os.path.join(d, f) for f in sorted(os.listdir(d)) if re.match(r"^\d+-.*\.my$", f) and not f.endswith(".solution.my")]
    return out


def header(path: str) -> dict:
    keys: dict = {"expect": [], "hint": [], "hidden": [], "own-tests": "0"}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^// ?([a-z-]+): ?(.*)$", line.rstrip("\n"))
            if not line.startswith("//"):
                break
            if m and m.group(1) in ("title", "xp", "boss", "expect", "hint", "hidden", "own-tests"):
                if m.group(1) in ("expect", "hint", "hidden"):
                    keys[m.group(1)].append(m.group(2))
                else:
                    keys[m.group(1)] = m.group(2)
    return keys


def starter(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    i = 0
    while i < len(lines) and lines[i].startswith("//"):
        i += 1
    return "\n".join(lines[i:])


_FUN = re.compile(r"^(\s*)(?:pub\s+)?(?:async\s+)?fun\s+([A-Za-z_][A-Za-z0-9_]*)\s*[<(]")


def _attribute_end(lines: list[str], i: int) -> int:
    depth, in_string = 0, False
    for j in range(i, len(lines)):
        k, line = 0, lines[j]
        while k < len(line):
            c = line[k]
            if in_string:
                if c == "\\":
                    k += 1
                elif c == '"':
                    in_string = False
            elif c == '"':
                in_string = True
            elif c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
            k += 1
        if depth <= 0 and re.search(r"[\])]\s*$", line):
            return j + 1
    return len(lines)


def tests_of(source: str) -> list[tuple[str, list[str]]]:
    lines, out, pending, i = source.split("\n"), [], [], 0
    while i < len(lines):
        t = lines[i].strip()
        if t.startswith("#test"):
            end = _attribute_end(lines, i)
            pending.append("\n".join(lines[i:end]).strip())
            i = end
            continue
        m = _FUN.match(lines[i])
        if m and pending:
            out.append((m.group(2), pending))
        if not t.startswith("#"):
            pending = []
        i += 1
    return out


def checked_program(code: str, own: list, hidden: list, own_tests: int) -> tuple[str, int] | None:
    """The program Check runs and its number of cases, or None when a tested function is gone."""
    lines = code.split("\n")
    if own_tests == 0:
        kept, i = [], 0
        while i < len(lines):
            if lines[i].strip().startswith("#test"):
                i = _attribute_end(lines, i)
                continue
            kept.append(lines[i])
            i += 1
        lines = kept
    add: dict[str, list[str]] = {}
    for fn, cs in (own if own_tests == 0 else []) + hidden:
        add.setdefault(fn, []).extend(cs)
    cases = 0
    for fn, cs in add.items():
        at = next((n for n, l in enumerate(lines) if (m := _FUN.match(l)) and m.group(2) == fn), -1)
        if at < 0:
            return None
        indent = _FUN.match(lines[at]).group(1)
        lines[at:at] = [indent + c for c in cs]
        cases += len(cs)
    if own_tests > 0:
        cases += sum(1 for l in code.split("\n") if l.strip().startswith("#test"))
    return "\n".join(lines), cases


def hidden_cases(h: dict) -> list[tuple[str, list[str]]]:
    out: dict[str, list[str]] = {}
    for v in h["hidden"]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s+(#test.*)$", v.strip())
        assert m, f"a hidden case is `// hidden: <function> #test(…)[…]`, not: {v}"
        out.setdefault(m.group(1), []).append(m.group(2))
    return list(out.items())


def solved(path: str, exercise: str) -> tuple[bool, str]:
    """Whether `path` solves `exercise` by the Check button's rules, and what it printed."""
    h = header(exercise)
    try:
        if h["expect"]:
            p = subprocess.run([selfhost_tool("main"), "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True, timeout=LIMIT)
            return p.returncode == 0 and p.stdout == "\n".join(h["expect"]) + "\n", p.stdout + p.stderr
        with open(path, encoding="utf-8") as fh:
            code = fh.read()
        own_tests = int(h["own-tests"])
        prog = checked_program(code, tests_of(starter(exercise)), hidden_cases(h), own_tests)
        if prog is None:
            return False, "(a tested function is missing)"
        if own_tests and sum(1 for l in code.split("\n") if l.strip().startswith("#test")) < own_tests:
            return False, f"(fewer than {own_tests} cases of the learner's own)"
        source, cases = prog
        with tempfile.NamedTemporaryFile("w", suffix=".my", delete=False, encoding="utf-8") as fh:
            fh.write(source)
        try:
            p = subprocess.run([selfhost_tool("main"), "test", fh.name, "--stdlib", STDLIB_ROOT], capture_output=True, text=True, timeout=LIMIT)
        finally:
            os.unlink(fh.name)
        m = re.search(r"(\d+)/(\d+) passed\.", p.stdout)
        ok = p.returncode == 0 and m is not None and m.group(1) == m.group(2) and int(m.group(2)) > 0 and int(m.group(2)) >= cases
        return ok, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return False, f"(still running after {LIMIT} s)"


class Course(unittest.TestCase):
    def test_every_exercise_is_unsolved_as_given_and_solved_by_its_solution(self) -> None:
        found = exercises()
        self.assertGreaterEqual(len(found), 42, "the course has the Answer's number of exercises at least")
        for ex in found:
            name = os.path.relpath(ex, LEARN)
            with self.subTest(exercise=name):
                given, out = solved(ex, ex)
                self.assertFalse(given, f"{name} is solved as given:\n{out}")
                sol, out = solved(ex[:-3] + ".solution.my", ex)
                self.assertTrue(sol, f"{name}'s solution doesn't solve it:\n{out}")

    def test_deleting_the_cases_for_a_trivial_one_does_not_pass(self) -> None:
        ex = os.path.join(LEARN, "01-dont-panic", "03-let-or-var.my")
        cheat = "#test(0)[0]\nfun triangle(n: int) -> int {\n    return 0\n}\n"
        with tempfile.NamedTemporaryFile("w", suffix=".my", delete=False, encoding="utf-8") as fh:
            fh.write(cheat)
        try:
            ok, out = solved(fh.name, ex)
        finally:
            os.unlink(fh.name)
        self.assertFalse(ok, out)
        self.assertEqual(checked_program("#test(1)[2]\nfun f(x: int) -> int { return x }\n", [], [], 0), ("fun f(x: int) -> int { return x }\n", 0))
        self.assertIsNone(checked_program("fun g() {}\n", [("f", ["#test()[1]"])], [], 0))

    def test_the_files_are_well_formed(self) -> None:
        for ch in sorted(os.listdir(LEARN)):
            d = os.path.join(LEARN, ch)
            if not (os.path.isdir(d) and re.match(r"^\d+-", ch)):
                continue
            with self.subTest(chapter=ch):
                with open(os.path.join(d, "chapter.md"), encoding="utf-8") as fh:
                    self.assertRegex(fh.readline(), r"^title: \S")
                bosses = 0
                for ex in [e for e in exercises() if os.path.dirname(e) == d]:
                    h = header(ex)
                    self.assertTrue(h.get("title"), f"{ex} has no title")
                    self.assertGreater(int(h.get("xp", "0")), 0, f"{ex} has no xp")
                    self.assertTrue(h["hint"], f"{ex} has no hint")
                    self.assertTrue(os.path.exists(ex[:-3] + ".solution.my"), f"{ex} has no solution")
                    bosses += h.get("boss") == "true"
                self.assertEqual(bosses, 1, f"{ch} has {bosses} bosses")


class Samples(unittest.TestCase):
    def test_the_landing_page_samples_print_their_output(self) -> None:
        for f in sorted(os.listdir(SAMPLES)):
            path = os.path.join(SAMPLES, f)
            with self.subTest(sample=f):
                with open(path, encoding="utf-8") as fh:
                    text = fh.read().rstrip().split("\n")
                at = text.index("// output:")
                want = "\n".join("" if l == "//" else l[3:] for l in text[at + 1:]) + "\n"
                p = subprocess.run([selfhost_tool("main"), "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True, timeout=60)
                self.assertEqual((p.stdout, p.stderr, p.returncode), (want, "", 0))


class Reference(unittest.TestCase):
    def test_tools_doc_documents_the_standard_library(self) -> None:
        std = os.path.join(_REPO, "lib", "std")
        internal = {"rt", "platform", "platform_aarch64", "platform_wasm", "platform_windows", "slice"}
        modules = [os.path.join(std, f) for f in sorted(os.listdir(std)) if f.endswith(".my") and f[:-3] not in internal]
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "api.json")
            p = subprocess.run([myla_tool("tools/doc/main.my", "doc"), "-o", out, *modules], capture_output=True, text=True, timeout=300)
            self.assertEqual((p.stderr, p.returncode), ("", 0))
            with open(out, encoding="utf-8") as fh:
                api = {m["name"]: m for m in json.load(fh)}
        self.assertEqual(len(api), len(modules))
        vec3 = next(i for i in api["std.vector"]["items"] if i["name"] == "Vec3" and i["kind"] == "struct")
        self.assertEqual(vec3["signature"], "struct Vec3")
        self.assertEqual([m["name"] for m in vec3["members"]], ["x", "y", "z"])
        split = next(m for i in api["std.str"]["items"] if i["kind"] == "impl" for m in i["members"] if m["name"] == "split")
        self.assertTrue(split["doc"] and split["tests"], split)


if __name__ == "__main__":
    unittest.main()
