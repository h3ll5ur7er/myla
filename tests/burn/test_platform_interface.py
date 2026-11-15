"""Burn test: every platform module offers the same interface, in Myla's
terms (MYLA-701, D209).

`std.platform` is one module per target (`lib/std/platform.my` for x86-64
Linux, `platform_aarch64.my`, `platform_wasm.my`, `platform_windows.my`), which the
loader takes for `std/platform.my` on its target. std.rt and the library
above it are written once against it, so each must give the same functions
with the same types, and the same constants: the cause codes a failure gives
(std.ioerror's, which `from_cause` reads), the kinds of a file
(`KIND_FILE`, …, which std.fs and std.glob read), and what a target may lack
(`PROCESSES`, `SOCKETS`). This test holds them to it three ways:

- the declarations: every `pub fun` and `pub const` of each module, with its
  types (and a constant's value, but for those that tell the targets apart),
  against x86-64's;
- the types again, by the checker: a program that binds each function of
  x86-64's module to a variable of its function type, built for each target
  with that target's module;
- the behaviour: a program calling the platform's functions directly gives
  the same causes and kinds on the target the suite runs for
  (`scripts/test-target.py` runs it on aarch64 under qemu and on wasm32
  under Node).

And the copies of the numbering outside the platform modules agree with it:
std.ioerror's cause codes, std.rt's `CAUSE_NUMBERS`, std.fs's and std.glob's
kinds, std.process's `DIR_FAILED`."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest

from ._native import CAN_BUILD_NATIVE, SKIP_REASON, run_argv, target_flags, write_program
from ._tools import STDLIB_ROOT, selfhost_tool

STD = os.path.join(STDLIB_ROOT, "std")
MODULES = {"x86_64-linux": "platform.my", "aarch64-linux": "platform_aarch64.my", "wasm32-wasi": "platform_wasm.my",
           "x86_64-windows": "platform_windows.my"}
# the constants that tell the targets apart
PER_TARGET = {"TARGET", "RETURNS_MEMORY", "HUGE_PAGES", "PROCESSES", "SOCKETS"}
# a target's own entry points, which its back end calls by name
# (`backend_std_functions`): wasm32's and Windows' starts, which lay out the
# arguments
OWN = {"wasm32-wasi": {"wasm_start"}, "x86_64-windows": {"windows_start"}}
# the tools a build for a target needs besides the host's
BUILD_TOOLS = {"aarch64-linux": ["clang", "ld.lld"], "wasm32-wasi": ["clang", "wasm-ld"],
               "x86_64-windows": ["clang", "llvm-dlltool", "lld-link"]}

_FUN = re.compile(r"^pub fun ([a-z_0-9]+)\((.*)\)(?: -> (.+?))? \{$")
_CONST = re.compile(r"^pub const ([A-Z_0-9]+): ([a-z0-9]+) = (.+?)(?:\s*//.*)?$")


def _read(name: str) -> str:
    with open(os.path.join(STD, name), encoding="utf-8") as fh:
        return fh.read()


def _params(text: str) -> tuple[str, ...]:
    """The types of a parameter list `a: int64, b: str`."""
    return tuple(p.split(":", 1)[1].strip() for p in text.split(",") if p.strip())


def interface(name: str) -> tuple[dict[str, tuple], dict[str, tuple[str, str]]]:
    """The functions (name: parameter types and result) and the constants
    (name: type and value) a platform module declares `pub`."""
    funs, consts = {}, {}
    for line in _read(name).splitlines():
        m = _FUN.match(line)
        if m:
            funs[m.group(1)] = (_params(m.group(2)), m.group(3) or "()")
        m = _CONST.match(line)
        if m:
            consts[m.group(1)] = (m.group(2), m.group(3))
    return funs, consts


def private_consts(name: str) -> dict[str, str]:
    """The values of a module's constants, `pub` or not, by name."""
    return {m.group(1): m.group(2) for m in re.finditer(r"^(?:pub )?const ([A-Z_0-9]+): [a-z0-9]+ = (.+?)\s*$",
                                                        _read(name), re.M)}


class Declarations(unittest.TestCase):
    def test_every_module_has_the_same_functions_with_the_same_types(self):
        want, _ = interface(MODULES["x86_64-linux"])
        self.assertGreater(len(want), 80)
        for target, name in MODULES.items():
            got, _ = interface(name)
            with self.subTest(target=target):
                self.assertEqual(sorted(set(want) - set(got)), [], "missing")
                self.assertEqual(sorted(set(got) - set(want) - OWN.get(target, set())), [], "not in x86-64's")
                for f, sig in want.items():
                    self.assertEqual(got[f], sig, f)

    def test_every_module_has_the_same_constants(self):
        _, want = interface(MODULES["x86_64-linux"])
        self.assertIn("NOT_FOUND", want)
        self.assertIn("KIND_DIR", want)
        for target, name in MODULES.items():
            _, got = interface(name)
            with self.subTest(target=target):
                self.assertEqual(sorted(got), sorted(want))
                for c, (ty, value) in want.items():
                    self.assertEqual(got[c][0], ty, c)
                    if c not in PER_TARGET:
                        self.assertEqual(got[c][1], value, c)
                self.assertEqual(got["TARGET"][1], f'"{target}"')

    def test_no_errno_crosses_the_interface(self):
        # what MYLA-265 found: Linux's errnos, records and mode bits above
        # the platform modules
        _, consts = interface(MODULES["x86_64-linux"])
        for gone in ("EINTR", "EAGAIN", "EPIPE"):
            self.assertNotIn(gone, consts)
        funs, _ = interface(MODULES["x86_64-linux"])
        self.assertNotIn("mode_of", funs)
        for f in ("path_kind", "dir_entry_name_len", "dir_entry_kind"):
            self.assertIn(f, funs)
        rt = _read("rt.my")
        self.assertFalse(re.search(r"os\.E[A-Z]+|__set_io_errno\([1-9]", rt), "std.rt sets a number of its own")
        for name in ("fs.my", "glob.my"):
            self.assertFalse("S_IFMT" in _read(name), name)
        for name in ("fs.my", "io.my", "process.my", "net.my", "http.my", "term.my", "signal.my"):
            self.assertFalse(re.search(r"from_errno\(|const E[A-Z]+: int", _read(name)), name)

    def test_the_numbering_outside_agrees(self):
        _, platform = interface(MODULES["x86_64-linux"])
        causes = {c: v for c, (ty, v) in platform.items() if ty == "int64" and not c.startswith("KIND_")}
        ioerror = private_consts("ioerror.my")
        for c, v in causes.items():
            self.assertEqual(ioerror.get(c), v, f"std.ioerror's {c}")
        self.assertEqual(private_consts("rt.my")["CAUSE_NUMBERS"], ioerror["LINUX_NUMBERS"])
        kinds = {c: v for c, (_, v) in platform.items() if c.startswith("KIND_")}
        for name in ("fs.my", "glob.my"):
            for c, v in private_consts(name).items():
                if c.startswith("KIND_"):
                    self.assertEqual(kinds[c], v, f"{name}'s {c}")
        dir_failed = private_consts("process.my")["DIR_FAILED"]
        for target in ("x86_64-linux", "aarch64-linux"):     # wasm32 and Windows have none yet
            self.assertEqual(private_consts(MODULES[target])["DIR_FAILED"], dir_failed, target)


def bindings_program() -> str:
    """A program that binds every function of x86-64's module to a variable
    of its type, and every constant to one of its type, in a function nothing
    calls: checked, never compiled (taking `cpus_allowed` as a value would
    link the runtime's variables of tasks)."""
    funs, consts = interface(MODULES["x86_64-linux"])
    lines = ["import std.platform as os", "", "fun bindings() {"]
    for f, (params, result) in sorted(funs.items()):
        lines.append(f"    let f_{f}: ({', '.join(params)}) -> {result} = os.{f}")
    for c, (ty, _) in sorted(consts.items()):
        lines.append(f"    let c_{c.lower()}: {ty} = os.{c}")
    lines += ["}", "", "fun main() {", '    print("ok")', "}"]
    return "\n".join(lines) + "\n"


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Types(unittest.TestCase):
    def test_each_target_checks_the_interface(self):
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, bindings_program())
            for target in MODULES:
                if not all(shutil.which(t) for t in BUILD_TOOLS.get(target, [])):
                    continue
                with self.subTest(target=target):
                    proc = subprocess.run([myla, "build", path, "-o", os.path.join(tmp, "out"), "--stdlib", STDLIB_ROOT,
                                           "--target", target], capture_output=True, text=True)
                    self.assertEqual((proc.stderr, proc.returncode), ("", 0))

    def test_a_different_type_is_caught(self):
        # the check above would see a module whose function differs
        myla = selfhost_tool("main")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, "import std.platform as os\n\nfun main() {\n"
                                      "    let f: (int64) -> int64 = os.path_kind\n}\n")
            proc = subprocess.run([myla, "check", path, "--stdlib", STDLIB_ROOT], capture_output=True, text=True)
            self.assertIn("type error", proc.stderr)


# The platform's functions called directly, their results in Myla's terms:
# minus a cause code (std.ioerror's `from_cause` names it), a kind, a
# directory's entries as names and kinds. A module of the library's (raw
# memory is the library's only, D100), put in a copy of it; the test makes
# `f.txt`, and `sub/` with `g.txt` and `deeper/` in it, first.
PROBE = """import .platform as os
import .ioerror as ioerror

fun said(r: int64) -> str {
    if r >= 0 {
        return f"{r}"
    }
    return ioerror.io_error_name(ioerror.from_cause((-r) as int32))
}

// The entries of the directory `path` but `.` and `..`, as `name kind`,
// sorted, through `dir_read` and the accessors.
fun entries(path: str) -> [str] {
    var out: [str] = []
    let fd = os.open_dir(path)
    if fd < 0 {
        out.push(said(fd))
        return out
    }
    let buf = __alloc(4096)
    while true {
        let got = os.dir_read(fd, buf, 4096)
        if got <= 0 {
            break
        }
        var at: int64 = 0
        while at < got {
            let rec = buf + at
            let n = os.dir_entry_name_len(rec)
            let cell = __alloc(n + 8)
            __store64(cell, n)
            __copy_bytes(cell + 8, os.dir_entry_name(rec), n)
            let name = __str_of(cell)
            if name != "." && name != ".." {
                out.push(f"{name} {os.dir_entry_kind(rec)}")
            }
            at += os.dir_entry_size(rec)
        }
    }
    __free(buf)
    let c = os.close(fd)
    return sorted(out)
}

// `xs` sorted (an insertion sort: std.list isn't this module's).
fun sorted(xs: [str]) -> [str] {
    var out: [str] = []
    for x in xs {
        var i = out.len()
        out.push(x)
        while i > 0 && out[i - 1] > x {
            out[i] = out[i - 1]
            i -= 1
        }
        out[i] = x
    }
    return out
}

pub fun probe(dir: str) {
    print(said(os.open_read(dir + "/missing")))
    print(said(os.path_kind(dir)))
    print(said(os.path_kind(dir + "/f.txt")))
    print(said(os.path_kind(dir + "/missing")))
    print(said(os.make_dir(dir + "/sub", 493)))
    print(said(os.remove_dir(dir + "/sub")))
    print(said(os.remove_dir(dir + "/f.txt")))
    print(said(os.open_dir(dir + "/f.txt")))
    print(said(os.close(-1)))
    let out = __alloc(48)
    print(said(os.path_stat(dir + "/f.txt", true, out)))
    print(f"{__load64(out)} {__load64(out + 8)}")
    print(said(os.path_stat(dir + "/sub", false, out)))
    print(__load64(out + 8))
    __free(out)
    for e in entries(dir + "/sub") {
        print(e)
    }
    for e in entries(dir + "/missing") {
        print(e)
    }
    print(os.PROCESSES == (os.TARGET != "wasm32-wasi" && os.TARGET != "x86_64-windows"))
    if !os.PROCESSES {
        let none: [str] = []
        let h = os.spawn_piped(["true"], ["true"], none)
        print(h[0] as int64 == os.UNSUPPORTED)
    } else {
        print(true)
    }
}
"""
BEHAVIOUR = """import std.interface_probe as probe
from std.process import args

fun main() {
    probe.probe(args()[1])
}
"""
BEHAVIOUR_OUT = """NotFound
2
1
NotFound
AlreadyExists
NotEmpty
NotADirectory
NotADirectory
Other(9)
0
5 1
0
2
deeper 2
g.txt 1
NotFound
true
true
"""


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Behaviour(unittest.TestCase):
    def test_causes_and_kinds_on_the_target(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as src:
            data = os.path.join(tmp, "data")
            os.makedirs(os.path.join(data, "sub", "deeper"))
            with open(os.path.join(data, "f.txt"), "w") as fh:
                fh.write("hello")
            with open(os.path.join(data, "sub", "g.txt"), "w") as fh:
                fh.write("g")
            lib = os.path.join(src, "lib")
            shutil.copytree(STDLIB_ROOT, lib)
            with open(os.path.join(lib, "std", "interface_probe.my"), "w") as fh:
                fh.write(PROBE)
            path = write_program(src, BEHAVIOUR)
            binary = os.path.join(src, "prog")
            proc = subprocess.run([selfhost_tool("main"), "build", path, "-o", binary, "--stdlib", lib,
                                   *target_flags()], capture_output=True, text=True)
            self.assertEqual((proc.stderr, proc.returncode), ("", 0))
            argv, exe = run_argv(binary, path, [data])
            run = subprocess.run(argv, executable=exe, capture_output=True, text=True)
        self.assertEqual((run.stdout, run.stderr, run.returncode), (BEHAVIOUR_OUT, "", 0))


if __name__ == "__main__":
    unittest.main()
