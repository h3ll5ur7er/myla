"""Burn tests: the toolchain's huge pages for the heap (MYLA-608).

std.rt's `heap_huge_pages` advises the heap's chunks from then on
(`MADV_HUGEPAGE`), and the rest of the arena from its next 2 MiB boundary,
so a fault there maps 2 MiB instead of 4 KB. `myla`, `gen_main` and the
language server call it at their start; a program `myla build` builds
doesn't, and asks for none. Measured in minor page faults (`ru_minflt`), which
huge pages make a hundred times fewer; skipped where the kernel has no
transparent huge pages, or gives them to every program anyway (`always`)."""
import os
import tempfile
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON
from tests.burn._tools import STDLIB_ROOT, selfhost_tool


def _thp_mode() -> str:
    """The kernel's transparent huge pages mode (`always`, `madvise`,
    `never`), "" without them."""
    try:
        with open("/sys/kernel/mm/transparent_hugepage/enabled", encoding="ascii") as fh:
            text = fh.read()
    except OSError:
        return ""
    return text[text.index("[") + 1:text.index("]")] if "[" in text else ""


_THP = _thp_mode()

# about 12 MB of small cells, with the opt-in when it has an argument; with
# tasks (`#main async`) its chunks are mapped aligned, else as they come
_ALLOCATES = """from std.process import args
from std.rt import heap_huge_pages

MAIN {
    if args().len() > 1 {
        heap_huge_pages()
    }
    var xs: [str] = []
    for i in 0..200000 {
        xs.push(f"cell {i} of a heap that grows by 4 KB pages or by 2 MiB ones")
    }
    print(xs.len())
}
"""


def _faults(argv, env=None) -> tuple[str, int]:
    """(stdout, minor page faults) of running `argv`."""
    with tempfile.TemporaryFile() as out:
        pid = os.posix_spawn(argv[0], argv, env or os.environ,
                             file_actions=[(os.POSIX_SPAWN_DUP2, out.fileno(), 1)])
        _, status, usage = os.wait4(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0, argv
        out.seek(0)
        return out.read().decode(), usage.ru_minflt


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
@unittest.skipUnless(_THP == "madvise", f"transparent huge pages are {_THP or 'missing'}, not on madvise")
class HugePages(unittest.TestCase):
    def test_the_opt_in_maps_the_heap_in_huge_pages(self):
        for tasks in [False, True]:
            with self.subTest(tasks=tasks):
                self.opt_in(_ALLOCATES.replace("MAIN", "#main\nasync fun main()" if tasks else "fun main()"))

    def opt_in(self, source: str):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "allocates.my")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(source)
            exe = os.path.join(tmp, "allocates")
            _, built = _faults([selfhost_tool("main"), "build", src, "-o", exe, "--stdlib", STDLIB_ROOT])
            self.assertTrue(os.path.exists(exe), built)
            env = dict(os.environ, MYLA_THREADS="1")
            plain_out, plain = _faults([exe], env)
            huge_out, huge = _faults([exe, "huge"], env)
            self.assertEqual((plain_out, huge_out), ("200000\n", "200000\n"))
            # a program that doesn't ask faults each 4 KB page of its heap:
            # it pays nothing at its start
            self.assertGreater(plain, 2000)
            self.assertLess(huge * 10, plain, f"{huge} faults with huge pages, {plain} without")

    def test_a_check_takes_few_faults(self):
        # `myla check` of a hello world touches about 4 MB of fresh heap:
        # about 1,100 faults before the opt-in, 110 after (MYLA-608)
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "hello.my")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write('fun main() { print("hello") }\n')
            out, faults = _faults([selfhost_tool("main"), "check", src], dict(os.environ, MYLA_THREADS="1"))
            self.assertEqual(out, "ok\n")
            self.assertLess(faults, 400)


if __name__ == "__main__":
    unittest.main()
