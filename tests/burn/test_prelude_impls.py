"""Burn test: the prelude's derived `Eq` and `Hash` of `Option` and `Result`
(D182, MYLA-417) are checked once a program compares or hashes a type that
holds one, and each way of doing so is seen.

Their bodies (and std.hash's methods they call) wait so that a hello world's
check costs no more than it did before `Hash` was derived (`prelude_need` in
selfhost/checker.my). A way the checker missed would leave a body unchecked
that a runner calls; each program here uses exactly one way, so each must
run alike interpreted and natively and print what it should."""
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_source_both_now

_KEY = """#derive(Eq, Hash)
struct Key {
    name: str,
    port: Option<int>,
}
"""

# (name, program, expected output): each compares or hashes an `Option` or a
# `Result` in one way only
_PROGRAMS = [
    ("map key", "fun main() {\n    var m: [Option<int>: int] = [:]\n    m[Some(2)] = 5\n    m[None] = 1\n"
                "    m[Some(2)] = m[Some(2)] + 1\n    print(m[Some(2)] + m[None])\n}\n", "7\n"),
    ("tuple key", "fun main() {\n    var m: [(str, Result<int, str>): int] = [:]\n    m[(\"a\", Ok(1))] = 3\n"
                  "    print(m.contains((\"a\", Ok(1))))\n    print(m.contains((\"a\", Err(\"x\"))))\n}\n", "true\nfalse\n"),
    ("a derived key's member", _KEY + "fun main() {\n    var m: [Key: int] = [:]\n    m[Key { name: \"a\", port: None }] = 1\n"
                               "    m[Key { name: \"a\", port: Some(1) }] = 2\n    print(m.len())\n"
                               "    print(m[Key { name: \"a\", port: None }])\n}\n", "2\n1\n"),
    ("a derived Eq's member", "#derive(Eq)\nstruct P {\n    v: Option<str>,\n}\n"
                              "fun main() {\n    let a = P { v: Some(\"x\") }\n    let b = P { v: Some(\"x\") }\n"
                              "    let c = P { v: None }\n    print(a == b)\n    print(a == c)\n}\n", "true\nfalse\n"),
    ("==", "fun main() {\n    let a: Option<int> = Some(3)\n    print(a == Some(3))\n    print(None == a)\n}\n", "true\nfalse\n"),
    ("a list's ==", "fun main() {\n    let a = [Some(1), None]\n    print(a == [Some(1), None])\n    print(a == [None, None])\n}\n",
     "true\nfalse\n"),
    ("a bound", "fun same<T: Eq>(a: T, b: T) -> bool {\n    return a == b\n}\n"
                "fun main() {\n    print(same(Some(1), Some(1)))\n    let r: Result<int, str> = Ok(1)\n    print(same(r, Err(\"e\")))\n}\n", "true\nfalse\n"),
    ("a hasher", "fun main() {\n    let h = Hasher { state: 1 }\n    print(h.add(Some(5)).finish() == h.add(Some(5)).finish())\n"
                 "    print(h.add(Some(5)).finish() == h.add(Some(6)).finish())\n}\n", "true\nfalse\n"),
    ("a method", "fun main() {\n    let o: Option<str> = Some(\"q\")\n    let h = Hasher { state: 1 }\n"
                 "    print(o.hash(h).finish() == h.add(o).finish())\n    print(o.eq(Some(\"q\")))\n}\n", "true\ntrue\n"),
    ("a list method", "fun main() {\n    let xs = [None, Some(4)]\n    print(xs.contains(Some(4)))\n}\n", "true\n"),
    ("none", "fun main() {\n    let o: Option<int> = Some(1)\n    print(o.unwrap_or(0))\n}\n", "1\n"),
]


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class PreludeImpls(unittest.TestCase):
    def test_each_use_checks_them(self):
        for name, src, want in _PROGRAMS:
            with self.subTest(use=name):
                self.assertEqual(run_source_both_now(src), (want, "", 0))


if __name__ == "__main__":
    unittest.main()
