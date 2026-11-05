"""Burn test: the unit type `()` (D138, MYLA-278).

`()` is a type with one value, also written `()`: what `Result<(), E>` gives
when a function succeeds with nothing to give. It takes no memory, so a list of
units holds only its length. The self-hosted interpreter and native code agree."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_source_both_now
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

PROGRAM = """fun save(ok: bool) -> Result<(), str> {
    if !ok {
        return Err("refused")
    }
    return Ok(())
}

fun twice(ok: bool) -> Result<int, str> {
    save(ok)?
    save(ok)?
    return Ok(2)
}

fun same<T>(x: T) -> T {
    return x
}

#derive(Eq)
struct Mark {
    seen: (),
    n: int,
}

enum Step {
    Done(()),
    More(int),
}

fun nothing() -> () {
    return ()
}

async fun job(ok: bool) -> Result<(), str> {
    return save(ok)
}

fun shown(r: Result<(), str>) -> str {
    return match r {
        Ok(()) => "ok"
        Err(e) => "err " + e
    }
}

#main
async fun main() {
    let u: () = ()
    print(u == ())
    print(u != nothing())
    print(shown(save(true)))
    print(shown(save(false)))
    print(match twice(true) { Ok(n) => n, Err(_) => -1 })
    print(match twice(false) { Ok(n) => n, Err(_) => -1 })
    var xs: [()] = [(), ()]
    xs.push(())
    print(xs.len())
    let set: [str: ()] = ["a": (), "b": ()]
    print(set.len())
    print(set.contains("b"))
    let o: Option<()> = Some(())
    if let Some(()) = o {
        print("some")
    }
    let pair = ((), 7)
    print(pair.1)
    let ((), seven) = pair
    print(seven)
    print(same(()) == ())
    print(Mark { seen: (), n: 1 } == Mark { seen: (), n: 1 })
    let steps = [Step.Done(()), Step.More(3)]
    for s in steps {
        match s {
            Done(()) => print("done")
            More(k) => print(k)
        }
    }
    let f: (int) -> () = (x: int) => ()
    print(f(1) == ())
    async let a = job(true)
    async let b = job(false)
    print(shown(await a))
    print(shown(await b))
}
"""

WANT = ("true\nfalse\nok\nerr refused\n2\n-1\n3\n2\ntrue\nsome\n7\n7\ntrue\ntrue\ndone\n3\ntrue\nok\nerr refused\n")


# D140: a function without a result type returns `()`
VOID = """fun log(s: str) {
    print(s)
}

fun shout(s: str) -> () {
    print(s + "!")
    return ()
}

fun twice(f: (str) -> (), s: str) {
    f(s)
    f(s)
    return
}

fun wrap(ok: bool) -> Result<(), str> {
    if !ok {
        return Err("no")
    }
    return Ok(log("wrapped"))
}

fun pick(k: int) -> (str) -> () {
    if k > 0 {
        return log
    }
    return shout
}

fun main() {
    let u = log("a")
    print(u == ())
    print(shout("b") == log("c"))
    twice(log, "d")
    twice(shout, "e")
    let f: (str) -> () = (s: str) => print("[" + s + "]")
    twice(f, "f")
    pick(0)("g")
    pick(1)("h")
    match wrap(true) {
        Ok(()) => print("ok")
        Err(e) => print(e)
    }
    let xs: [()] = [log("i"), ()]
    print(xs.len())
}
"""

VOID_WANT = "a\ntrue\nb!\nc\ntrue\nd\nd\ne!\ne!\n[f]\n[f]\ng!\nh\nwrapped\nok\ni\n2\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class UnitType(unittest.TestCase):
    def test_a_function_without_a_result_returns_unit(self):
        self.assertEqual(run_source_both_now(VOID), (VOID_WANT, "", 0))

    def test_in_the_interpreter_and_natively(self):
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_a_unit_test_names_the_value(self):
        src = ("#test(true)[Ok(())]\n#test(false)[Err(\"no\")]\nfun f(ok: bool) -> Result<(), str> {\n"
               "    if ok {\n        return Ok(())\n    }\n    return Err(\"no\")\n}\n\nfun main() {\n}\n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
            proc = subprocess.run([selfhost_tool("main"), "test", path, "--stdlib", STDLIB_ROOT],
                                  capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("2 passed", proc.stdout + proc.stderr)

    def test_errors(self):
        cases = {
            "not_a_number": ("fun main() {\n    let u = ()\n    print(u + 1)\n}\n", "type error"),
            "ordered": ("fun main() {\n    print(() < ())\n}\n", "comparison requires numeric or char operands"),
            "not_an_int": ("fun main() {\n    let x: int = ()\n}\n", "type error"),
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


if __name__ == "__main__":
    unittest.main()
