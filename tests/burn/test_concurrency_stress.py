"""Burn tests: the concurrency stress tests (MYLA-144), Myla's answers to the
language-neutral plan in docs/Development/Concurrency-stress-tests.md.

Each program in tests/burn/concurrency_stress/ states what Myla guarantees
for its example; it must print the same on the self-hosted interpreter and
natively on 1, 4 and 16 workers (several runs each), under a watchdog (and on
the Python interpreter until it was retired, MYLA-219), and in other orders
of its tasks: on one worker, the interpreter and native code alike, oldest
first and in the orders of a few seeds (MYLA_SCHED, D110, MYLA-231), each
reproducible. The examples Myla
rejects at compile time are in the error corpus (examples/errors/), the
documented limits on the Concurrency page."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT
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
    # 6. an actor's state checked again after an `await` (without the second
    # check a warning says it may have changed, D95)
    "t06_recheck_after_the_await": ("successes 1 stock 0\n", 0),
    # 7. a cancelled worker gives back what it holds, wherever it was asked to
    # stop: cancellation is a flag it checks (D96)
    "t07_cancelled_holder_gives_back": (
        "0: stopped before taking, available 1, duplicates 0\n"
        "1: stopped holding, gave back, available 1, duplicates 0\n"
        "2: stopped using, gave back, available 1, duplicates 0\n"
        "3: stopped using, gave back, available 1, duplicates 0\n"
        "4: stopped using, gave back, available 1, duplicates 0\n"
        "5: stopped done using, gave back, available 1, duplicates 0\n"
        "6: stopped after giving back, available 1, duplicates 0\n", 0),
    # 8. a failure cancels the failing task's other children, which stop at
    # their next suspension point; it waits for them, then ends the program
    # (D94), where it used to wait forever for a looping sibling
    "t08_failure_cancels_a_looping_sibling": ("", 1),
    # ... and a failing child's own children, looping on an actor that the
    # rest of the program uses for ever; the failure reaches the program at
    # once, so the entry stops at its next call of the actor (D97), as does a
    # parent waiting for another child
    "t08_failing_child_cancels_its_children": ("", 1),
    "t08_failure_reaches_a_waiting_parent": ("", 1),
    "t08_group_fails_fast": ("", 1),
    # ... reported at once while a sibling computes without a suspension
    # point, which ends the program once it reaches one (MYLA-170)
    "t15_failure_beside_a_busy_sibling": ("", 1),
    # 9. "latest request wins" is the program's to say: a request number
    "t09_latest_request_wins": ("ui shows cats\n", 0),
    # ... or by cancelling the old request, which checks before publishing
    "t09_cancel_the_stale_request": ("ui shows cats\n", 0),
    # 14. an awaited `var self` method of a struct in an actor's field works on
    # a copy and writes it back when it returns (D99, MYLA-169): changes made
    # one after the other are kept, a change made while it waits is replaced
    "t14_struct_method_in_actor": ("101000\n1 1 1\n", 0),
    # 13. a child task of an actor method works on what the method read into
    # a `let` (reaching `self` is rejected, MYLA-168)
    "t13_child_of_an_actor_method": ("true\n", 0),
    # ... and a loop or match over a field of `self` across an `await` holds
    # its own references (MYLA-198: native code hung on 4 workers)
    "t13_actor_state_across_an_await": ("true\n", 0),
    # 16. lines longer than a pipe keeps whole, printed in the parent's order
    # from what its children returned (MYLA-173)
    "t16_long_lines": ("".join(c * 6000 + "\n" for c in "abcd") + "24000\n", 0),
    # 10. what an actor publishes is seen whole
    "t10_publication_through_an_actor": ("42\n", 0),
    # 12. every worker and every single request make progress
    "t12_progress_under_contention": ("workers done 8 of 8\nsingles done 50, greedy stopped\n", 0),
}


# the orders other than the default (newest first) each program is run in
SCHEDULES = ["fifo", "seed:1", "seed:2", "seed:3"]


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

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_the_self_hosted_interpreter(self):
        from ._tools import selfhost_tool
        interp = selfhost_tool("interp_main")
        for name, want in EXPECTED.items():
            with self.subTest(program=name):
                got = _run([interp, os.path.join(_DIR, name + ".my"), STDLIB_ROOT])
                self.assertEqual(got, want)

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_natively_on_any_number_of_workers(self):
        from ._tools import selfhost_tool
        gen = selfhost_tool("gen_main")
        for name, want in EXPECTED.items():
            with self.subTest(program=name), tempfile.TemporaryDirectory() as tmp:
                exe = os.path.join(tmp, name)
                asm = subprocess.run([gen, os.path.join(_DIR, name + ".my"), STDLIB_ROOT],
                                     capture_output=True, text=True, check=True).stdout
                with open(exe + ".s", "w", encoding="utf-8") as fh:
                    fh.write(asm)
                subprocess.run(["gcc", "-nostdlib", "-static", "-o", exe, exe + ".s"], check=True)
                for workers in ["1", "4", "16"]:
                    for _ in range(3):
                        got = _run([exe], dict(os.environ, MYLA_THREADS=workers))
                        self.assertEqual(got, want, f"{workers} workers")
                for sched in SCHEDULES:
                    got = _run([exe], dict(os.environ, MYLA_THREADS="1", MYLA_SCHED=sched))
                    self.assertEqual(got, want, f"MYLA_SCHED={sched}")

    @unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
    def test_the_self_hosted_interpreter_in_other_orders(self):
        from ._tools import selfhost_tool
        interp = selfhost_tool("interp_main")
        for name, want in EXPECTED.items():
            for sched in SCHEDULES:
                with self.subTest(program=name, sched=sched):
                    got = _run([interp, os.path.join(_DIR, name + ".my"), STDLIB_ROOT],
                               dict(os.environ, MYLA_SCHED=sched))
                    self.assertEqual(got, want)


if __name__ == "__main__":
    unittest.main()
