"""Burn test: default parameter values (D136, MYLA-255).

A function's or method's trailing parameters may have defaults; a call may
leave out a suffix of them, and the caller evaluates each default it leaves
out, at each call. Defaults belong to the declaration: a function value takes
every argument. The self-hosted interpreter and native code agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_argv, target_flags
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

_PROGRAM = """struct Conn {
    host: str,
    port: int,
    retries: int,
}

fun connect(host: str, port: int = 80, retries: int = 3) -> Conn {
    return Conn { host: host, port: port, retries: retries }
}

fun shown(c: Conn) -> str {
    return f"{c.host}:{c.port} x{c.retries}"
}

const BASE: int = 10

fun scaled(x: int, by: int = BASE * 2) -> int {
    return x * by
}

fun greet(name: str = "world") -> str {
    return "hello " + name
}

struct Counter {
    n: int,
}

impl Counter {
    fun add(self, k: int = 1) -> Counter {
        return Counter { n: self.n + k }
    }
}

fun count_down(n: int, acc: int = 0) -> int {
    if n == 0 {
        return acc
    }
    become count_down(n - 1, acc + n)
}

fun count_from(n: int) -> int {
    become count_down(n)
}

fun nested(x: int = scaled(2)) -> int {
    return x + 1
}

async fun fetch(id: int, tries: int = 2) -> int {
    return id * 10 + tries
}

#main
async fun main() {
    print(shown(connect("example.org")))
    print(shown(connect("example.org", 8080)))
    print(shown(connect("example.org", 8080, 5)))
    print(scaled(3))
    print(scaled(3, 2))
    print(greet())
    print(greet("myla"))
    let c = Counter { n: 1 }
    print(c.add().add(5).n)
    print(count_from(10))
    print(nested())
    print(nested(7))
    let f = connect
    print(shown(f("h", 1, 2)))
    print(3 |> scaled())
    async let a = fetch(1)
    print(await a)
    print(await fetch(2, 7))
}
"""

_WANT = ("example.org:80 x3\nexample.org:8080 x3\nexample.org:8080 x5\n60\n6\nhello world\nhello myla\n7\n55\n41\n8\n"
         "h:1 x2\n60\n12\n27\n")


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class DefaultParams(unittest.TestCase):
    def setUp(self) -> None:
        self.myla = selfhost_tool("main")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name: str, src: str) -> str:
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        return path

    def test_in_the_interpreter_and_natively(self):
        path = self.write("defaults.my", _PROGRAM)
        proc = subprocess.run([self.myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True,
                              timeout=60)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))
        exe = os.path.join(self.tmp.name, "defaults")
        built = subprocess.run([self.myla, "build", path, "-o", exe, "--stdlib", STDLIB_ROOT, *target_flags()], capture_output=True,
                               text=True)
        self.assertEqual(built.returncode, 0, built.stderr)
        proc = subprocess.run(run_argv(exe, exe)[0], capture_output=True, text=True, timeout=60)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), (_WANT, "", 0))

    def test_a_split_ge_before_a_default(self):
        # `Option<int>= None`: the `>=` splits, the `=` starts a default (it
        # was a syntax error before D136)
        path = self.write("split.my", "fun f(x: Option<int>= None) -> int {\n    return match x { Some(v) => v, None => -1 }\n}\n\n"
                                      "fun main() {\n    print(f())\n    print(f(Some(4)))\n}\n")
        proc = subprocess.run([self.myla, "run", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
        self.assertEqual((proc.stdout, proc.stderr, proc.returncode), ("-1\n4\n", "", 0))

    def test_errors(self):
        cases = {
            "too_few": ("fun f(a: int, b: int = 2) -> int {\n    return a + b\n}\n\nfun main() {\n    print(f())\n}\n",
                        "type error: function 'f' expects 1 to 2 argument(s), got 0"),
            "too_many": ("fun f(a: int = 1) -> int {\n    return a\n}\n\nfun main() {\n    print(f(1, 2))\n}\n",
                         "type error: function 'f' expects 0 to 1 argument(s), got 2"),
            "not_trailing": ("fun f(a: int = 1, b: int) -> int {\n    return a + b\n}\n\nfun main() {\n    print(f(1, 2))\n}\n",
                             "type error: parameter 'b' needs a default: the parameters after one with a default have one too"),
            "wrong_type": ("fun f(a: int = \"x\") -> int {\n    return a\n}\n\nfun main() {\n    print(f())\n}\n",
                           "type error"),
            "names_a_parameter": ("fun f(a: int, b: int = a) -> int {\n    return b\n}\n\nfun main() {\n    print(f(1))\n}\n",
                                  "type error: unknown name 'a'"),
            "generic": ("fun f<T>(x: T, y: [T] = []) -> int {\n    return y.len()\n}\n\nfun main() {\n    print(f(1))\n}\n",
                        "type error: parameter 'y' can't have a default: its type mentions a type parameter"),
            "function_value": ("fun f(a: int, b: int = 2) -> int {\n    return a + b\n}\n\nfun main() {\n    let g = f\n    print(g(1))\n}\n",
                               "type error: this function value expects 2 argument(s), got 1"),
            "trait": ("trait T {\n    fun m(self, k: int = 1) -> int\n}\n\nfun main() {\n}\n",
                      "type error: the methods of a trait can't have default values"),
        }
        for name, (src, want) in cases.items():
            with self.subTest(case=name):
                path = self.write(name + ".my", src)
                proc = subprocess.run([self.myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                                      text=True)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertIn(want, proc.stderr)


if __name__ == "__main__":
    unittest.main()
