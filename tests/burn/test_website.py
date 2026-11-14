"""Burn test: what the website runs is right (D208, MYLA-159).

- Every exercise of the course (learn/, MYLA-634) is not solved as given and
  is solved by its solution, by the rules the site's Check button applies: an
  exercise with `// expect:` lines prints exactly them, one without passes all
  its #test cases (at least one); ten seconds is the limit, as in the browser.
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
    keys: dict = {"expect": [], "hint": []}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^// ?([a-z]+): ?(.*)$", line.rstrip("\n"))
            if not line.startswith("//"):
                break
            if m and m.group(1) in ("title", "xp", "boss", "expect", "hint"):
                if m.group(1) in ("expect", "hint"):
                    keys[m.group(1)].append(m.group(2))
                else:
                    keys.setdefault(m.group(1), m.group(2))
    return keys


def solved(path: str, expect: list[str]) -> tuple[bool, str]:
    """Whether `path` is solved, and what it printed."""
    try:
        if expect:
            p = subprocess.run([selfhost_tool("main"), "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True, timeout=LIMIT)
            return p.returncode == 0 and p.stdout == "\n".join(expect) + "\n", p.stdout + p.stderr
        p = subprocess.run([selfhost_tool("main"), "test", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True, timeout=LIMIT)
        m = re.search(r"(\d+)/(\d+) passed\.", p.stdout)
        ok = p.returncode == 0 and m is not None and m.group(1) == m.group(2) and int(m.group(2)) > 0
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
                expect = header(ex)["expect"]
                given, out = solved(ex, expect)
                self.assertFalse(given, f"{name} is solved as given:\n{out}")
                sol, out = solved(ex[:-3] + ".solution.my", expect)
                self.assertTrue(sol, f"{name}'s solution doesn't solve it:\n{out}")

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
        internal = {"rt", "platform", "platform_aarch64", "platform_wasm", "slice"}
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
