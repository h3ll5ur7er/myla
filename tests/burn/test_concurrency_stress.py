"""Burn tests: the concurrency stress tests (MYLA-144), Myla's answers to the
language-neutral plan in docs/Development/Concurrency-stress-tests.md.

Each program in tests/burn/concurrency_stress/ states what Myla guarantees
for its example; it must print the same on the Python interpreter, the
self-hosted interpreter and natively on 1, 4 and 16 workers (several runs
each), under a watchdog. The examples Myla rejects at compile time are in the
error corpus (examples/errors/), the documented limits on the Concurrency
page."""
import os
import subprocess
import sys
import tempfile
import unittest

from myla.loader import default_stdlib_root
from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "concurrency_stress")
_WATCHDOG = 60

# program -> (stdout, exit code): what Myla guarantees for it
EXPECTED = {
    # 1. a shared counter is an actor: its methods run one at a time
    "t01_shared_counter_actor": ("200000\n", 0),
    # 2. check-then-act in one synchronous actor method is one step
    "t02_check_then_act": ("1 20\n", 0),
    # 3. an invariant over two parts kept in one actor holds
    "t03_invariant_in_one_actor": ("invariant true\n", 0),
    # 4. no locks, reentrant actors whose executors never block a worker: no
    # deadlock, the total kept, a self-transfer leaves the balance
    "t04_transfers_both_ways": ("11000 -9000 total 2000\n", 0),
    # 5. a child may await an earlier sibling (MYLA-148): no cycle can form
    "t05_child_awaits_sibling": ("2\n", 0),
    "t05_siblings_share_a_result": ("60780\n", 0),
    # 8. a failure cancels the failing task's other children, which stop at
    # their next suspension point; it waits for them, then ends the program
    # (D94), where it used to wait forever for a looping sibling
    "t08_failure_cancels_a_looping_sibling": ("", 1),
    # ... and a failing child's own children, looping on an actor that the
    # rest of the program goes on using
    "t08_failing_child_cancels_its_children": ("main still runs\n", 1),
    # 10. what an actor publishes is seen whole
    "t10_publication_through_an_actor": ("42\n", 0),
    # 12. every worker and every single request make progress
    "t12_progress_under_contention": ("workers done 8 of 8\nsingles done 50, greedy stopped\n", 0),
}


def _run(cmd, env=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=_WATCHDOG, env=env)
        return p.stdout, p.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1


class ConcurrencyStress(unittest.TestCase):
    def test_every_program_has_its_expectation(self):
        programs = sorted(f[:-3] for f in os.listdir(_DIR) if f.endswith(".my"))
        self.assertEqual(programs, sorted(EXPECTED))

    def test_the_python_interpreter(self):
        for name, want in EXPECTED.items():
            with self.subTest(program=name):
                got = _run([sys.executable, os.path.join(_REPO, "myla.py"), "run",
                            os.path.join(_DIR, name + ".my")])
                self.assertEqual(got, want)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_the_self_hosted_interpreter(self):
        from ._tools import selfhost_tool
        interp = selfhost_tool("interp_main")
        for name, want in EXPECTED.items():
            with self.subTest(program=name):
                got = _run([interp, os.path.join(_DIR, name + ".my"), default_stdlib_root()])
                self.assertEqual(got, want)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_natively_on_any_number_of_workers(self):
        from ._tools import selfhost_tool
        gen = selfhost_tool("gen_main")
        for name, want in EXPECTED.items():
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                exe = os.path.join(tmp, name)
                asm = subprocess.run([gen, os.path.join(_DIR, name + ".my"), default_stdlib_root()],
                                     capture_output=True, text=True, check=True).stdout
                with open(exe + ".s", "w", encoding="utf-8") as fh:
                    fh.write(asm)
                subprocess.run(["gcc", "-nostdlib", "-static", "-o", exe, exe + ".s"], check=True)
                for workers in ["1", "4", "16"]:
                    for _ in range(3):
                        got = _run([exe], dict(os.environ, MYLA_THREADS=workers))
                        self.assertEqual(got, want, f"{workers} workers")


if __name__ == "__main__":
    unittest.main()
