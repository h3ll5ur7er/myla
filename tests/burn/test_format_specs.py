"""Burn test: format specs in f-strings and `format` (D139, MYLA-277).

`{expression:spec}`, the spec Rust's `[[fill]align][sign][#][0][width]
[.precision][kind]`, checked against the value's type when the program is
compiled; a user's type implementing `Format` gets the spec's text as it is.
The formatting is Myla (`std.fmt`, `std.num`), so the interpreter and every
backend print the same bytes. (A float without a precision prints as `print`
prints it: 17 significant digits, so 0.1 is 0.10000000000000001.)"""
import os
import subprocess
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_source_both_now
from tests.burn._tools import STDLIB_ROOT, selfhost_tool

PROGRAM = """import std.fmt as fmt

struct Date {
    y: int,
    m: int,
    d: int,
}

impl Format for Date {
    fun format(self, spec: str) -> str {
        return match spec {
            "" => f"{self.y:04}-{self.m:02}-{self.d:02}"
            "dmy" => f"{self.d:02}.{self.m:02}.{self.y}"
            _ => fmt.pad(self.format(""), spec)
        }
    }
}

fun main() {
    let pi = 3.14159265
    print(f"{pi:.2}")
    print(f"[{42:>6}]")
    print(f"[{42:<6}]")
    print(f"[{42:^6}]")
    print(f"[{42:^7}]")
    print(f"{7:03}")
    print(f"{-7:04}")
    print(f"{7:+}")
    print(f"{7:*>4} {7::>3}")
    print(f"{255:x} {255:X} {255:b} {255:o}")
    print(f"{255:#06x} {5:#b} {8:#o} {255:#X}")
    print(f"{5:08b}")
    print(f"{-1i8:x} {-1i8:08b}")
    print(f"{255:1x}")
    print(f"{2.675:.2} {0.125:.2} {0.375:.2}")
    print(f"{1.0:.0} {2.5:.0} {3.5:.0}")
    print(f"{-1.5:+.1} {1.5:+.1}")
    print(f"[{3.5:8.2}] [{3.5:<8.2}] [{3.5:08.2}] [{-3.5:08.2}]")
    print(f"[{0.5:>6}]")
    print(f"[{"ab":^6}] [{"ab":>4}] [{"ab"}]")
    print(f"[{"λ":>3}]")
    print(f"[{'c':>3}] [{true:>6}] [{false:<6}]")
    print(f"[{"toolong":3}]")
    let d = Date { y: 2026, m: 11, d: 5 }
    print(f"{d} {d:dmy} [{d:>12}]")
    print(format("{:>5}|{:<5}|{}", 1, 2, 3))
    print("[" + fmt.pad("x", "^5") + "]")
    let big: uint64 = 18446744073709551615
    print(f"{big:x} {big}")
    let m: int64 = -9223372036854775808
    print(f"{m:+} {m:x}")
    print(f"{1e21:.1}")
    print(f"{1.0e-7:.3}")
    print(f"{-0.0001:.2}")
    let xs = [1, 2, 3]
    print(f"{xs.len():>3}|{xs[1]:03}")
}
"""

WANT = """3.14
[    42]
[42    ]
[  42  ]
[  42   ]
007
-007
+7
***7 ::7
ff FF 11111111 377
0x00ff 0b101 0o10 0xFF
00000101
ff 11111111
ff
2.67 0.12 0.38
1 2 4
-1.5 +1.5
[    3.50] [3.50    ] [00003.50] [-0003.50]
[   0.5]
[  ab  ] [  ab] [ab]
[  λ]
[  c] [  true] [false ]
[toolong]
2026-11-05 05.11.2026 [  2026-11-05]
    1|2    |3
[  x  ]
ffffffffffffffff 18446744073709551615
-9223372036854775808 8000000000000000
1000000000000000000000.0
0.000
-0.00
  3|002
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class FormatSpecs(unittest.TestCase):
    def test_in_the_interpreter_and_natively(self):
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    def test_errors(self):
        cases = {
            "precision_on_an_int": ('fun main() {\n    print(f"{5:.2}")\n}\n',
                                    "the format spec '.2' needs a float, found 'int32'"),
            "kind_on_a_float": ('fun main() {\n    print(f"{1.5:x}")\n}\n',
                                "the format spec 'x' needs an integer, found 'float64'"),
            "sign_on_text": ('fun main() {\n    print(f"{"a":+}")\n}\n',
                             "the format spec '+' needs a number, found 'str'"),
            "alternate_without_a_kind": ('fun main() {\n    print(f"{5:#}")\n}\n',
                                         "the format spec '#' needs a kind: x, X, b or o"),
            "unknown": ('fun main() {\n    print(f"{5:q}")\n}\n', "invalid format spec 'q'"),
            "width_too_large": ('fun main() {\n    print(f"{5:9999999999}")\n}\n', "invalid format spec '9999999999': a width above 1000000"),
            "precision_too_large": ('fun main() {\n    print(f"{1.5:.4294967297}")\n}\n', "invalid format spec '.4294967297': a precision above 1000000"),
            "a_point_without_digits": ('fun main() {\n    print(f"{1.5:.}")\n}\n', "invalid format spec '.'"),
            "in_format": ('fun main() {\n    print(format("{:.1}", 3))\n}\n',
                          "the format spec '.1' needs a float, found 'int32'"),
            "no_format": ("struct P {\n    x: int,\n}\n\nfun main() {\n    let p = P { x: 1 }\n    print(f\"{p}\")\n}\n",
                          "format() cannot render a value of type 'P'"),
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
                    self.assertIn("type error: " + want, proc.stderr)


if __name__ == "__main__":
    unittest.main()
