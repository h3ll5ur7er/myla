"""Burn test: `await task.yield()` (D107, MYLA-228).

`task.yield()` is a suspension point and nothing else: the other ready tasks
run, and a task that a failure stopped notices it there (D97). A sibling that
loops for ever without one keeps a failing task from ending the program on one
worker (the documented limit, MYLA-170); with `await task.yield()` in its loop
the failure ends the program at once, in the self-hosted interpreter and
natively on any number of workers. Like any async function it must be awaited."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_SPIN = """import std.task as task

async fun spin() -> int {
    var i = 0
    while true {
        i = i + 1
        await task.yield()
    }
    return i
}

async fun fail_soon() -> int {
    panic("failure beside a spinning sibling")
    return 0
}

#main
async fun main() {
    // the spinning task the newer, so it runs first on one worker (D110)
    async let b = fail_soon()
    async let a = spin()
    print(await a + await b)
}
"""

_TURNS = """import std.task as task

async fun count(name: str, n: int) -> int {
    for i in 0..n {
        print(f"{name} {i}")
        await task.yield()
    }
    return n
}

#main
async fun main() {
    async let a = count("a", 3)
    async let b = count("b", 3)
    print(await a + await b)
}
"""

_UNAWAITED = """import std.task as task

#main
async fun main() {
    task.yield()
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class TaskYield(unittest.TestCase):
    def setUp(self) -> None:
        self.myla = selfhost_tool("main")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, src: str) -> str:
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        return path

    def both(self, path: str, workers: list[str]):
        """(stdout, stderr's first line, exit) of the interpreter, then of the
        native binary on each number of workers."""
        runs = []
        proc = subprocess.run([self.myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                              text=True, timeout=30)
        runs.append(("interpreter", proc))
        exe = path[:-3]
        subprocess.run([self.myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT], check=True,
                       capture_output=True)
        for w in workers:
            runs.append((f"{w} workers", subprocess.run([exe], capture_output=True, text=True, timeout=30,
                                                         env=dict(os.environ, MYLA_THREADS=w))))
        return [(name, (p.stdout, p.stderr.split("\n")[0], p.returncode)) for name, p in runs]

    def test_a_spinning_sibling_that_yields_lets_a_failure_end_the_program(self):
        path = self.write("spin.my", _SPIN)
        for name, got in self.both(path, ["1", "4"]):
            with self.subTest(runner=name):
                self.assertEqual(got, ("", "runtime error: failure beside a spinning sibling", 1))

    def test_tasks_take_turns_at_each_yield(self):
        # one worker: the order of the interpreter, depth first (D110)
        path = self.write("turns.my", _TURNS)
        results = dict(self.both(path, ["1"]))
        self.assertEqual(results["interpreter"], results["1 workers"])
        out = results["interpreter"][0].split("\n")
        self.assertEqual(sorted(out[:6]), ["a 0", "a 1", "a 2", "b 0", "b 1", "b 2"])
        self.assertEqual(out[6:], ["6", ""])
        # the two tasks interleave: neither runs all its turns first
        self.assertNotIn(out[:3], (["a 0", "a 1", "a 2"], ["b 0", "b 1", "b 2"]))

    def test_it_must_be_awaited(self):
        path = self.write("unawaited.my", _UNAWAITED)
        proc = subprocess.run([self.myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                              text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("needs 'await'", proc.stderr)


if __name__ == "__main__":
    unittest.main()
