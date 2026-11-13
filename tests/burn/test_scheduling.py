"""Burn tests: the order tasks run in (D110, MYLA-231).

Every runner runs the newest ready task first (depth first), a task yielding
its turn goes behind the others, and an ended child's result comes at once;
`MYLA_SCHED=fifo` runs the oldest first, `MYLA_SCHED=seed:N` one picked by a
generator seeded with N. On one worker the self-hosted interpreter and native
code run tasks in the same order whichever of them is chosen
(`data/sched_order.my` prints where each task is), and depth first a tree of
tasks needs memory for its depth, not its width."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_ORDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sched_order.my")

# The program reports its own peak resident memory (`VmHWM`, kB): a child's
# `ru_maxrss` counts the image `fork` copied from the test's process too
# (Linux takes the old image's high-water mark at `exec`), so it read 234 MB
# under the full suite, whose one process had grown that big (MYLA-611).
_WIDE = """import std.task as task
import std.fs as fs

#main
async fun main() {
    var fns: [async () -> int] = []
    for i in 0..300000 {
        let k = i
        fns.push(async () => k)
    }
    let r = await task.all(fns)
    print(r.len())
    if let Ok(s) = fs.read_to_string("/proc/self/status") {
        for l in s.split("\\n") {
            if l.starts_with("VmHWM:") {
                print(l[6:].trim())
            }
        }
    }
}
"""


def _peak_mb(cmd, env) -> tuple[str, float]:
    """(its first line, its peak resident memory in MB) of running `cmd`,
    which prints them (`_WIDE`)."""
    out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120, check=True).stdout
    first, peak = out.split("\n")[:2]
    assert peak.endswith(" kB"), out
    return first + "\n", int(peak[:-3]) / 1024


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Scheduling(unittest.TestCase):
    def build(self, src_path: str, tmp: str) -> str:
        exe = os.path.join(tmp, "prog")
        subprocess.run([selfhost_tool("main"), "build", src_path, "-o", exe, "--stdlib", STDLIB_ROOT],
                       check=True, capture_output=True)
        return exe

    def test_one_worker_runs_tasks_in_the_interpreters_order(self):
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            exe = self.build(_ORDER, tmp)
            seen = set()
            for sched in ["", "lifo", "fifo", "seed:1", "seed:99", "seed:4242"]:
                with self.subTest(sched=sched):
                    env = dict(os.environ, MYLA_SCHED=sched, MYLA_THREADS="1")
                    native = subprocess.run([exe], capture_output=True, text=True, env=env, timeout=60)
                    interp = subprocess.run([myla, "run", _ORDER, "--stdlib", STDLIB_ROOT],
                                            capture_output=True, text=True, env=env, timeout=60)
                    self.assertEqual((native.returncode, interp.returncode), (0, 0))
                    self.assertEqual(native.stdout, interp.stdout)
                    seen.add(native.stdout)
            # the default is lifo; the other orders differ from it and from
            # each other
            self.assertEqual(len(seen), 5)

    def test_depth_first_order_runs_the_newest_task_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = self.build(_ORDER, tmp)
            out = subprocess.run([exe], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, MYLA_THREADS="1")).stdout.split("\n")
            # `task.all` splits its list in halves, the second half's child
            # the newer: the last function runs first
            self.assertEqual(out[:3], ["f4", "f3", "f3."])
            out = subprocess.run([exe], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, MYLA_THREADS="1", MYLA_SCHED="fifo")).stdout.split("\n")
            self.assertEqual(out[:3], ["f0", "f1", "f1."])

    def test_a_wide_tree_of_tasks_needs_memory_for_its_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "wide.my")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(_WIDE)
            exe = self.build(src, tmp)
            lifo_out, lifo = _peak_mb([exe], dict(os.environ, MYLA_THREADS="1"))
            fifo_out, fifo = _peak_mb([exe], dict(os.environ, MYLA_THREADS="1", MYLA_SCHED="fifo"))
            self.assertEqual((lifo_out, fifo_out), ("300000\n", "300000\n"))
            # breadth first holds every task's frame at once: several times more
            self.assertLess(lifo * 3, fifo, f"lifo {lifo:.0f} MB, fifo {fifo:.0f} MB")


if __name__ == "__main__":
    unittest.main()
