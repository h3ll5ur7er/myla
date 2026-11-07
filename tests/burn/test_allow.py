"""Burn test: `#allow` (D161, MYLA-285). A warning shows its name
(`warning[primitive]: …`), and `#allow(name)` on a function, a method or an
impl block silences it there; `#allow(primitive(__a, __b))` silences those
primitives only. An error can't be allowed, and a name no warning has is
a warning itself."""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

CLOCK = "fun main() {\n    print(__clock_ns() > 0)\n}\n"

TWO = """ATTRfun main() {
    print(__clock_ns() > 0)
    print(__getcwd().len() > 0)
}
"""

IMPL = """struct Probe {
    n: int,
}

ATTRimpl Probe {
    fun now(self) -> bool {
        return __clock_ns() > 0
    }
}

fun main() {
    print(Probe { n: 1 }.now())
}
"""

ACTOR = """actor Auditor {
    seen: int,
}

impl Auditor {
    fun record(var self, amount: int) {
        self.seen = self.seen + amount
    }
}

actor Account {
    balance: int,
}

ATTRimpl Account {
    async fun pay_out(var self, amount: int, audit: Auditor) -> bool {
        if self.balance < amount { return false }
        await audit.record(amount)
        self.balance = self.balance - amount
        return true
    }
}

#main
async fun main() {
    let a = Account { balance: 10 }
    let au = Auditor { seen: 0 }
    print(await a.pay_out(3, au))
}
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Allow(unittest.TestCase):
    def check(self, source: str) -> tuple[str, int]:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "main.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(source)
            p = subprocess.run([selfhost_tool("main"), "check", path, "--stdlib", STDLIB_ROOT], capture_output=True,
                               text=True)
            return p.stderr, p.returncode

    def test_a_warning_shows_its_name(self):
        err, code = self.check(CLOCK)
        self.assertEqual(code, 0, err)
        self.assertIn("warning[primitive]: '__clock_ns' is a primitive of the standard library", err)
        err, code = self.check(ACTOR.replace("ATTR", ""))
        self.assertIn("warning[reentrancy]: 'self.balance' was checked before an 'await'", err)

    def test_allow_on_a_function(self):
        self.assertEqual(self.check(TWO.replace("ATTR", "#allow(primitive)\n")), ("", 0))
        # only the primitives named
        err, code = self.check(TWO.replace("ATTR", "#allow(primitive(__clock_ns))\n"))
        self.assertEqual(code, 0, err)
        self.assertNotIn("'__clock_ns'", err)
        self.assertIn("warning[primitive]: '__getcwd' is a primitive", err)

    def test_allow_on_an_impl_block(self):
        self.assertIn("warning[primitive]", self.check(IMPL.replace("ATTR", ""))[0])
        self.assertEqual(self.check(IMPL.replace("ATTR", "#allow(primitive)\n")), ("", 0))
        self.assertEqual(self.check(ACTOR.replace("ATTR", "#allow(reentrancy)\n")), ("", 0))
        # a method's own
        method = IMPL.replace("ATTR", "").replace("    fun now", "    #allow(primitive)\n    fun now")
        self.assertEqual(self.check(method), ("", 0))

    def test_a_name_no_warning_has(self):
        err, code = self.check(TWO.replace("ATTR", "#allow(primitive, unused)\n"))
        self.assertEqual(code, 0, err)
        self.assertIn("'unused' is no warning's name: '#allow' takes 'primitive' and 'reentrancy'", err)
        # on an impl block: once, not once per method
        err, code = self.check(IMPL.replace("ATTR", "#allow(unused)\n").replace("    fun now", "    fun other(self) -> int {\n        return 1\n    }\n\n    #allow(primitive)\n    fun now"))
        self.assertEqual((err.count("is no warning's name"), code), (1, 0), err)

    def test_errors(self):
        cases = {
            "raw_memory": ("#allow(primitive(__load64))\nfun main() {\n}\n",
                           "'__load64' reads or writes raw memory, which is an error outside the standard library: "
                           "'#allow' silences warnings only"),
            "on_a_struct": ("#allow(primitive)\nstruct P {\n    x: int,\n}\n\nfun main() {\n}\n",
                            "'#allow' stands on a function or an impl block"),
            "no_names": ("#allow()\nfun main() {\n}\n", "'#allow' names the warnings it silences"),
            "a_list_on_another": ("#allow(reentrancy(__poll))\nfun main() {\n}\n", "only 'primitive' takes a list"),
            "not_a_primitive": ("#allow(primitive(print))\nfun main() {\n}\n", "lists primitives, such as '__poll'"),
            "on_another_attribute_place": ("#test()[1]\nimpl P {\n}\n\nstruct P {\n    x: int,\n}\n\nfun main() {\n}\n",
                                           "type error"),
        }
        for name, (src, want) in cases.items():
            with self.subTest(case=name):
                err, code = self.check(src)
                self.assertEqual(code, 1, err)
                self.assertIn(want, err)


if __name__ == "__main__":
    unittest.main()
