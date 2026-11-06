"""Burn test: `defer` (D135, MYLA-229).

`defer { … }` runs its block when the enclosing block ends, the last one
registered first: at its end, at `return`, `?`, `break` and `continue`, and
before the call of a `become`. Not on a failure, which ends the program (D97).
The block reads the variables as they are when it runs, and the names it saw
where it stands. The self-hosted interpreter and native code agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_argv, run_source_both_now, target_flags
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

PROGRAM = """import std.task as task

fun ends() {
    defer {
        print("first registered, last run")
    }
    defer {
        print("last registered, first run")
    }
    print("body")
}

fun early(n: int) -> int {
    var steps = 0
    defer {
        print(f"leaving early({n}) after {steps} steps")
    }
    while steps < 10 {
        steps += 1
        if steps == n {
            return steps * 100
        }
    }
    return -1
}

fun parse(s: str) -> Option<int> {
    defer {
        print("parse " + s + " done")
    }
    if s == "" {
        return None
    }
    return Some(s.len())
}

fun total(a: str, b: str) -> Option<int> {
    defer {
        print("total done")
    }
    let x = parse(a)?
    let y = parse(b)?
    return Some(x + y)
}

fun loops() {
    for i in 0..4 {
        defer {
            print(f"turn {i} ends")
        }
        if i == 1 {
            continue
        }
        if i == 3 {
            break
        }
        print(f"turn {i}")
    }
}

fun countdown(n: int, acc: int) -> int {
    defer {
        if n % 25000 == 0 {
            print(f"frame {n} left")
        }
    }
    if n == 0 {
        return acc
    }
    become countdown(n - 1, acc + 1)
}

fun read_at_exit() -> int {
    var x = 1
    defer {
        print(f"x is {x} at the end")
    }
    x = 2
    return x
}

fun hygiene() {
    let name = "outer"
    defer {
        print("the deferred block sees " + name)
    }
    if true {
        let name = "inner"
        print("the block has " + name)
        return
    }
}

fun nested() {
    defer {
        defer {
            print("inner deferred")
        }
        print("outer deferred")
        var k = 0
        while true {
            k += 1
            if k == 3 {
                break
            }
        }
        print(f"k = {k}")
    }
    print("nested body")
}

// (the children print nothing: on several workers they run in parallel,
// and the order of their lines would be the timing's; test_one_worker
// checks the order where it is defined)
async fun child(n: int) -> int {
    await task.yield()
    return n * 2
}

async fun parent() -> int {
    defer {
        print("parent's deferred block, after its child")
    }
    async let a = child(7)
    print("parent waits")
    return await a
}

async fun ticks(n: int) -> int {
    var sum = 0
    for i in 0..n {
        defer {
            sum += i
        }
        await task.yield()
    }
    return sum
}

async fun slow(n: int) -> int {
    await task.yield()
    return n
}

// each scope left in turn: its children end, then its deferred blocks run
async fun scopes(n: int) -> int {
    defer {
        print("outer deferred")
    }
    async let a = slow(1)
    if n > 0 {
        defer {
            print("inner deferred")
        }
        return n
    }
    return await a
}

fun arms(o: Option<int>) {
    match o {
        Some(v) => {
            defer {
                print("the arm ends")
            }
            print(v)
        }
        None => print("none")
    }
}

#main
async fun main() {
    ends()
    print(early(3))
    print(early(20))
    print(match total("ab", "cde") { Some(v) => v, None => -1 })
    print(match total("", "x") { Some(v) => v, None => -1 })
    loops()
    print(countdown(100000, 0))
    print(read_at_exit())
    hygiene()
    nested()
    print(await parent())
    print(await ticks(4))
    let twice = (x: int) => {
        defer {
            print("the lambda leaves")
        }
        return x * 2
    }
    print(twice(4))
    arms(Some(9))
    arms(None)
    print(await scopes(5))
}
"""

WANT = """body
last registered, first run
first registered, last run
leaving early(3) after 3 steps
300
leaving early(20) after 10 steps
-1
parse ab done
parse cde done
total done
5
parse  done
total done
-1
turn 0
turn 0 ends
turn 1 ends
turn 2
turn 2 ends
turn 3 ends
frame 100000 left
frame 75000 left
frame 50000 left
frame 25000 left
frame 0 left
100000
x is 2 at the end
2
the block has inner
the deferred block sees outer
nested body
outer deferred
k = 3
inner deferred
parent waits
parent's deferred block, after its child
14
6
the lambda leaves
8
9
the arm ends
none
inner deferred
outer deferred
5
"""

# On one worker the order of tasks is defined (D110): a scope's children end
# before its deferred blocks run, scope by scope.
ONE_WORKER = """import std.task as task

async fun slow(n: int) -> int {
    await task.yield()
    print(f"slow {n} ends")
    return n
}

async fun scopes(n: int) -> int {
    defer {
        print("outer deferred")
    }
    async let a = slow(1)
    if n > 0 {
        defer {
            print("inner deferred")
        }
        return n
    }
    return await a
}

#main
async fun main() {
    print(await scopes(5))
}
"""

ONE_WORKER_WANT = "inner deferred\nslow 1 ends\nouter deferred\n5\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Defer(unittest.TestCase):
    def test_in_the_interpreter_and_natively(self):
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_one_worker(self):
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "one.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(ONE_WORKER)
            exe = os.path.join(tmp, "one")
            subprocess.run([myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT, *target_flags()], check=True)
            env = dict(os.environ, MYLA_THREADS="1")
            for runner, argv in (("run", [myla, "run", path, "--stdlib", STDLIB_ROOT]), ("native", run_argv(exe, exe)[0])):
                with self.subTest(argv=runner):
                    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60, env=env)
                    self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (ONE_WORKER_WANT, "", 0))

    def test_not_on_a_failure(self):
        # a failure ends the program at once (D97): `exit`, a panic
        src = ("from std.process import exit\n\nfun f(n: int) -> int {\n    defer {\n        print(\"not printed\")\n    }\n"
               "    if n > 0 {\n        exit(3)\n    }\n    return n\n}\n\nfun main() {\n    defer {\n        print(\"nor this\")\n    }\n"
               "    print(f(1))\n}\n")
        self.assertEqual(run_source_both_now(src), ("", "", 3))
        # (natively a panic's report has no source line: each on its own)
        src = ("fun main() {\n    defer {\n        print(\"not printed\")\n    }\n    panic(\"stop\")\n}\n")
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
            exe = os.path.join(tmp, "p")
            subprocess.run([myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT, *target_flags()], check=True)
            for runner, argv in (("run", [myla, "run", path, "--stdlib", STDLIB_ROOT]), ("native", run_argv(exe, exe)[0])):
                with self.subTest(argv=runner):
                    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
                    self.assertEqual((proc.stdout, proc.returncode), ("", 1))
                    self.assertIn("runtime error: stop", proc.stderr)

    def test_errors(self):
        loop = "fun main() {\n    while true {\n        defer {\n            BODY\n        }\n    }\n}\n"
        cases = {
            "return": ("fun f() -> int {\n    defer {\n        return 1\n    }\n    return 2\n}\n\nfun main() {\n}\n",
                       "a deferred block can't 'return'"),
            "become": ("fun g() -> int {\n    return 1\n}\n\nfun f() -> int {\n    defer {\n        become g()\n    }\n"
                       "    return 2\n}\n\nfun main() {\n}\n", "a deferred block can't 'become'"),
            "break": (loop.replace("BODY", "break"), "a deferred block can't 'break'"),
            "continue": (loop.replace("BODY", "continue"), "a deferred block can't 'continue'"),
            "try": ("fun f(o: Option<int>) -> Option<int> {\n    defer {\n        let x = o?\n    }\n    return o\n}\n\n"
                    "fun main() {\n}\n", "a deferred block can't use '?'"),
            "await": ("async fun g() -> int {\n    return 1\n}\n\nasync fun f() -> int {\n    defer {\n        let x = await g()\n"
                      "    }\n    return 2\n}\n\n#main\nasync fun main() {\n}\n", "a deferred block can't 'await'"),
            "async_let": ("async fun g() -> int {\n    return 1\n}\n\nasync fun f() -> int {\n    defer {\n"
                          "        async let x = g()\n    }\n    return 2\n}\n\n#main\nasync fun main() {\n}\n",
                          "a deferred block can't start a task"),
            "a_later_name": ("fun main() {\n    defer {\n        print(x)\n    }\n    let x = 1\n}\n", "unknown name 'x'"),
        }
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (src, want) in cases.items():
                with self.subTest(case=name):
                    path = os.path.join(tmp, name + ".my")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(src)
                    proc = subprocess.run([myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                                          text=True)
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertIn(want, proc.stderr)

    def test_allowed_inside(self):
        # a loop of its own may break and continue; a lambda may return
        src = ("fun main() {\n    defer {\n        for i in 0..5 {\n            if i == 1 {\n                continue\n"
               "            }\n            if i == 3 {\n                break\n            }\n            print(i)\n        }\n"
               "        let f = (x: int) => {\n            return x + 1\n        }\n        print(f(1))\n    }\n"
               "    print(\"main\")\n}\n")
        self.assertEqual(run_source_both_now(src), ("main\n0\n2\n2\n", "", 0))


if __name__ == "__main__":
    unittest.main()
