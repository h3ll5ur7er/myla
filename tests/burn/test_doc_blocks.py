"""Burn test: the Myla code in the documentation (D114, MYLA-233).

Every fenced block of the wiki (`docs/`) and the README whose info string is
`myla` is a program: it must type-check, and when it has a `main` it must run
in the self-hosted interpreter (in an empty directory, stdin empty) with exit
status 0, and natively print the same. A block may end with its output, which
must be exactly what it prints:

    // output:
    // 7
    // (3, -4)

(`//` alone stands for an empty line). Blocks that are deliberately pieces of
a program are marked `myla fragment` and only kept apart; blocks that are
deliberately wrong are marked `myla error` and must fail to check. The
convention is on the wiki page Development/Conventions."""
import glob
import os
import re
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_FENCE = re.compile(r"^(\s*)```(\S*)[ \t]*(.*)$")
_MAIN = re.compile(r"^(async )?fun main\(", re.M)


def blocks() -> list[tuple[str, int, str, str]]:
    """(file relative to the repository, line of the opening fence, kind:
    "myla", "fragment" or "error", source) of every `myla` block."""
    files = sorted(glob.glob(os.path.join(_REPO, "docs", "**", "*.md"), recursive=True))
    files.append(os.path.join(_REPO, "README.md"))
    out = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        i = 0
        while i < len(lines):
            m = _FENCE.match(lines[i])
            if m and m.group(2) != "":
                indent, lang, rest = m.group(1), m.group(2), m.group(3).strip()
                j = i + 1
                while j < len(lines) and not re.match(r"^\s*```\s*$", lines[j]):
                    j += 1
                if lang == "myla":
                    body = [ln[len(indent):] if ln.startswith(indent) else ln for ln in lines[i + 1:j]]
                    kind = rest if rest in ("fragment", "error") else "myla"
                    out.append((os.path.relpath(path, _REPO), i + 1, kind, "\n".join(body) + "\n"))
                i = j
            i += 1
    return out


def expected_output(source: str) -> str | None:
    """The block's `// output:` section, as the text it states is printed, or
    None without one."""
    lines = source.rstrip("\n").split("\n")
    for k in range(len(lines) - 1, -1, -1):
        if lines[k].strip() == "// output:":
            tail = lines[k + 1:]
            if all(ln.startswith("//") for ln in tail):
                return "".join((ln[3:] if ln.startswith("// ") else ln[2:]) + "\n" for ln in tail)
            return None
        if not lines[k].startswith("//"):
            return None
    return None


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class DocBlocks(unittest.TestCase):
    def setUp(self) -> None:
        self.myla = selfhost_tool("main")

    def run_myla(self, *args: str, cwd: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.myla, *args, "--stdlib", STDLIB_ROOT], capture_output=True,
                              text=True, cwd=cwd, stdin=subprocess.DEVNULL, timeout=60)

    def test_the_docs_have_blocks(self) -> None:
        found = blocks()
        self.assertGreater(len(found), 40)
        self.assertGreater(sum(1 for b in found if _MAIN.search(b[3]) and b[2] == "myla"), 30)

    def test_every_block_checks_runs_and_prints_its_output(self) -> None:
        for path, line, kind, source in blocks():
            if kind == "fragment":
                continue
            with self.subTest(block=f"{path}:{line}"), tempfile.TemporaryDirectory() as tmp:
                file = os.path.join(tmp, "main.my")
                with open(file, "w", encoding="utf-8") as fh:
                    fh.write(source)
                checked = self.run_myla("check", file, cwd=tmp)
                if kind == "error":
                    self.assertNotEqual(checked.returncode, 0, "a `myla error` block checks")
                    continue
                self.assertEqual(checked.returncode, 0, checked.stderr)
                want = expected_output(source)
                if not _MAIN.search(source):
                    self.assertIsNone(want, "an output section without a main")
                    continue
                ran = self.run_myla("run", file, cwd=tmp)
                self.assertEqual(ran.returncode, 0, ran.stderr)
                if want is not None:
                    self.assertEqual(ran.stdout, want)
                exe = os.path.join(tmp, "prog")
                built = self.run_myla("build", file, "-o", exe, cwd=tmp)
                self.assertEqual(built.returncode, 0, built.stderr)
                native = subprocess.run([exe], capture_output=True, text=True, cwd=tmp,
                                        stdin=subprocess.DEVNULL, timeout=60)
                self.assertEqual((native.stdout, native.returncode), (ran.stdout, 0))

    def test_output_sections_are_parsed(self) -> None:
        self.assertEqual(expected_output("fun main() {}\n// output:\n// 1\n//\n// a b\n"), "1\n\na b\n")
        self.assertIsNone(expected_output("fun main() {}\n// 1\n"))
        self.assertIsNone(expected_output("// output:\n// 1\nfun main() {}\n"))


if __name__ == "__main__":
    unittest.main()
