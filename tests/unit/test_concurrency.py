"""Unit tests for concurrency in the Python interpreter (D89, MYLA-136;
docs/Language/Concurrency.md): async functions, `await`, `async let`, actors.

Every expected output here is the same whatever order the tasks run in: the
order comes from `await`, from a scope waiting for its children, or from an
actor running one call at a time."""
import io
import unittest

from myla.errors import MylaRuntimeError
from myla.interpreter import Interpreter
from myla.lexer import tokenize
from myla.parser import parse
from myla.types import check


def run_src(src: str) -> str:
    out = io.StringIO()
    Interpreter(check(parse(tokenize(src))), out).run()
    return out.getvalue()


def run_main(body: str, pre: str = "") -> str:
    return run_src(f"{pre}#main\nasync fun main() {{\n{body}\n}}\n")


FETCH = "async fun fetch(n: int) -> int {\n    return n * 10\n}\n"

COUNTER = (
    "actor Counter {\n    count: int\n}\n"
    "impl Counter {\n"
    "    fun increment(var self) -> int {\n        self.count = self.count + 1\n        return self.count\n    }\n"
    "    fun get(self) -> int {\n        return self.count\n    }\n"
    "}\n"
)


class TestAsyncFunctions(unittest.TestCase):
    def test_await_a_call(self):
        self.assertEqual(run_main("    print(await fetch(4))", FETCH), "40\n")

    def test_await_inside_an_expression(self):
        self.assertEqual(run_main("    print(await fetch(1) + await fetch(2))", FETCH), "30\n")

    def test_async_lambda_and_function_value(self):
        src = FETCH + (
            "async fun apply(f: async (int) -> int, x: int) -> int {\n    return await f(x)\n}\n"
        )
        body = ("    let f = async (n: int) => await fetch(n) + 1\n"
                "    print(await apply(f, 2))\n"
                "    print(await apply(fetch, 3))")
        self.assertEqual(run_main(body, src), "21\n30\n")

    def test_async_method_of_a_struct(self):
        src = ("struct P { x: int }\nimpl P {\n"
               "    async fun twice(self) -> int {\n        return self.x * 2\n    }\n}\n")
        self.assertEqual(run_main("    let p = P { x: 21 }\n    print(await p.twice())", src), "42\n")


class TestAsyncLet(unittest.TestCase):
    def test_children_give_their_results(self):
        body = ("    async let a = fetch(1)\n    async let b: int = fetch(2)\n"
                "    print(await a + await b)")
        self.assertEqual(run_main(body, FETCH), "30\n")

    def test_awaiting_twice_gives_the_result_again(self):
        body = "    async let a = fetch(1)\n    print(await a)\n    print(await a)"
        self.assertEqual(run_main(body, FETCH), "10\n10\n")

    def test_a_scope_waits_for_children_never_awaited(self):
        src = "async fun noisy() {\n    print(\"child\")\n}\n"
        body = "    if true {\n        async let a = noisy()\n    }\n    print(\"after\")"
        self.assertEqual(run_main(body, src), "child\nafter\n")

    def test_a_loop_body_waits_for_its_children(self):
        src = "async fun noisy(i: int) {\n    print(i)\n}\n"
        body = "    for i in 0..3 {\n        async let a = noisy(i)\n    }\n    print(\"after\")"
        self.assertEqual(run_main(body, src), "0\n1\n2\nafter\n")

    def test_a_child_works_on_copies(self):
        src = ("async fun total(xs: [int]) -> int {\n    var t = 0\n"
               "    for x in xs {\n        t = t + x\n    }\n    return t\n}\n")
        body = ("    var xs = [1, 2, 3]\n    async let t = total(xs)\n"
                "    xs[0] = 100\n    print(await t)\n    print(xs[0])")
        self.assertEqual(run_main(body, src), "6\n100\n")

    def test_a_child_without_a_result(self):
        src = "async fun noisy() {\n    print(\"child\")\n}\n"
        body = "    async let a = noisy()\n    await a\n    print(\"after\")"
        self.assertEqual(run_main(body, src), "child\nafter\n")

    def test_an_awaited_childs_error_reaches_its_parent(self):
        src = "async fun boom() -> int {\n    panic(\"boom\")\n    return 0\n}\n"
        with self.assertRaises(MylaRuntimeError) as cm:
            run_main("    async let a = boom()\n    print(await a)", src)
        self.assertIn("boom", cm.exception.message)

    def test_an_error_of_a_child_never_awaited_ends_its_scope(self):
        src = "async fun boom() {\n    panic(\"boom\")\n}\n"
        with self.assertRaises(MylaRuntimeError) as cm:
            run_main("    if true {\n        async let a = boom()\n    }\n    print(\"after\")", src)
        self.assertIn("boom", cm.exception.message)

    def test_exit_in_a_child(self):
        src = ("from std.process import exit\n"
               "async fun leave() -> int {\n    exit(3)\n    return 0\n}\n")
        src += "#main\nasync fun main() {\n    async let a = leave()\n    print(await a)\n}\n"
        import os, tempfile
        from myla.loader import default_stdlib_root, link
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "leave.my")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
            checker = check(link(path, stdlib_root=default_stdlib_root()))
        out = io.StringIO()
        code = Interpreter(checker, out).run()
        self.assertEqual((code, out.getvalue()), (3, ""))


class TestActors(unittest.TestCase):
    def test_calls_run_one_at_a_time(self):
        src = COUNTER + (
            "async fun count_up(c: Counter, n: int) {\n"
            "    for i in 0..n {\n        let x = await c.increment()\n    }\n}\n"
        )
        body = ("    let c = Counter { count: 0 }\n"
                "    async let a = count_up(c, 500)\n    async let b = count_up(c, 500)\n"
                "    async let d = count_up(c, 500)\n"
                "    await a\n    await b\n    await d\n    print(await c.get())")
        self.assertEqual(run_main(body, src), "1500\n")

    def test_a_call_is_never_interleaved_with_another(self):
        # a read and a write apart, with the threads switching very often:
        # without the actor's lock, increments get lost
        import sys
        src = ("actor Counter {\n    count: int\n}\n"
               "impl Counter {\n    fun increment(var self) {\n        let v = self.count\n"
               "        var spin = 0\n        while spin < 20 {\n            spin = spin + 1\n        }\n"
               "        self.count = v + 1\n    }\n"
               "    fun get(self) -> int {\n        return self.count\n    }\n}\n"
               "async fun count_up(c: Counter, n: int) {\n"
               "    for i in 0..n {\n        await c.increment()\n    }\n}\n")
        body = ("    let c = Counter { count: 0 }\n"
                "    async let a = count_up(c, 300)\n    async let b = count_up(c, 300)\n"
                "    async let d = count_up(c, 300)\n"
                "    await a\n    await b\n    await d\n    print(await c.get())")
        interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            self.assertEqual(run_main(body, src), "900\n")
        finally:
            sys.setswitchinterval(interval)

    def test_a_copied_handle_reaches_the_same_actor(self):
        body = ("    let c = Counter { count: 0 }\n    let d = c\n"
                "    let x = await d.increment()\n    print(await c.get())")
        self.assertEqual(run_main(body, COUNTER), "1\n")

    def test_results_come_out_as_copies(self):
        src = ("actor Box {\n    items: [int]\n}\n"
               "impl Box {\n    fun all(self) -> [int] {\n        return self.items\n    }\n"
               "    fun first(self) -> int {\n        return self.items[0]\n    }\n}\n")
        body = ("    let b = Box { items: [1, 2] }\n    var xs = await b.all()\n"
                "    xs[0] = 9\n    print(await b.first())")
        self.assertEqual(run_main(body, src), "1\n")

    def test_arguments_go_in_as_copies(self):
        src = ("actor Box {\n    items: [int]\n}\n"
               "impl Box {\n    fun put(var self, xs: [int]) {\n        self.items = xs\n    }\n"
               "    fun first(self) -> int {\n        return self.items[0]\n    }\n}\n")
        body = ("    let b = Box { items: [] }\n    var xs = [1, 2]\n"
                "    await b.put(xs)\n    xs[0] = 9\n    print(await b.first())")
        self.assertEqual(run_main(body, src), "1\n")

    def test_methods_call_each_other_on_self(self):
        src = COUNTER.replace(
            "    fun get(self) -> int {",
            "    fun twice(var self) -> int {\n        let a = self.increment()\n"
            "        return self.increment()\n    }\n    fun get(self) -> int {")
        body = "    let c = Counter { count: 0 }\n    print(await c.twice())"
        self.assertEqual(run_main(body, src), "2\n")

    def test_reentrant_calls_back_into_a_waiting_actor(self):
        # A.ping waits on B.pong, which calls back into A: without reentrancy
        # this deadlocks
        src = ("actor A {\n    n: int\n}\nactor B {\n    m: int\n}\n"
               "impl A {\n    async fun ping(self, b: B) -> int {\n        return await b.pong(self)\n    }\n"
               "    fun val(self) -> int {\n        return self.n\n    }\n}\n"
               "impl B {\n    async fun pong(self, a: A) -> int {\n        return await a.val() + self.m\n    }\n}\n")
        body = ("    let a = A { n: 1 }\n    let b = B { m: 2 }\n"
                "    async let x = a.ping(b)\n    async let y = a.ping(b)\n"
                "    print(await x + await y)")
        self.assertEqual(run_main(body, src), "6\n")

    def test_two_actors_calling_each_other_from_two_tasks(self):
        # each task holds one actor and calls the other: releasing the actor at
        # the call keeps it from deadlocking
        src = ("actor P {\n    n: int\n}\n"
               "impl P {\n    async fun poke(self, other: P, depth: int) -> int {\n"
               "        if depth == 0 {\n            return self.n\n        }\n"
               "        return await other.poke(self, depth - 1) + self.n\n    }\n}\n")
        body = ("    let p = P { n: 1 }\n    let q = P { n: 10 }\n"
                "    async let x = p.poke(q, 50)\n    async let y = q.poke(p, 50)\n"
                "    print(await x)\n    print(await y)")
        self.assertEqual(run_main(body, src), "276\n285\n")

    def test_a_child_of_an_actor_method_reads_through_self(self):
        src = ("actor A {\n    n: int\n}\n"
               "impl A {\n    async fun peek(self) -> int {\n        async let x = self.n + 1\n"
               "        return await x\n    }\n}\n")
        self.assertEqual(run_main("    let a = A { n: 4 }\n    print(await a.peek())", src), "5\n")


def run_files(files: dict[str, str]) -> str:
    """Run `main.my` among `files` (name -> source), with the standard library."""
    import os, tempfile
    from myla.loader import default_stdlib_root, link
    with tempfile.TemporaryDirectory() as tmp:
        for name, src in files.items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(src)
        checker = check(link(os.path.join(tmp, "main.my"), stdlib_root=default_stdlib_root()))
    out = io.StringIO()
    Interpreter(checker, out).run()
    return out.getvalue()


class TestTaskAll(unittest.TestCase):
    def test_results_in_the_order_of_the_functions(self):
        src = ("import std.task as task\n" + FETCH +
               "#main\nasync fun main() {\n    var fs: [async () -> int] = []\n"
               "    for i in 0..37 {\n        push(fs, async () => await fetch(i))\n    }\n"
               "    let rs = await task.all(fs)\n    print(len(rs))\n    print(rs[0])\n    print(rs[36])\n"
               "    var ok = true\n    for i in 0..37 {\n        ok = ok && rs[i] == i * 10\n    }\n    print(ok)\n}\n")
        self.assertEqual(run_files({"main.my": src}), "37\n0\n360\ntrue\n")

    def test_no_functions(self):
        src = ("import std.task as task\n#main\nasync fun main() {\n"
               "    let none: [async () -> str] = []\n    print(len(await task.all(none)))\n}\n")
        self.assertEqual(run_files({"main.my": src}), "0\n")

    def test_children_update_an_actor(self):
        src = ("import std.task as task\n" + COUNTER +
               "#main\nasync fun main() {\n    let c = Counter { count: 0 }\n"
               "    var fs: [async () -> int] = []\n"
               "    for i in 0..20 {\n        push(fs, async () => await c.increment())\n    }\n"
               "    let rs = await task.all(fs)\n    print(await c.get())\n}\n")
        self.assertEqual(run_files({"main.my": src}), "20\n")


class TestModules(unittest.TestCase):
    def test_a_module_function_under_await(self):
        files = {
            "util.my": FETCH.replace("async fun", "pub async fun"),
            "main.my": ("import util as u\n#main\nasync fun main() {\n"
                        "    async let a = u.fetch(2)\n    print(await u.fetch(1) + await a)\n}\n"),
        }
        self.assertEqual(run_files(files), "30\n")


if __name__ == "__main__":
    unittest.main()
