"""Burn test: std.http's router (D202, MYLA-613).

A router holds routes (a method, a path pattern, a `(Request) -> Response`
handler) under a base path and is a handler itself, so routers nest
(`mount`), middleware wraps a handler (`wrap`) and static files are a route
(`static_files`). Patterns take `{name}`, `{name:int}` and a last
`{name:path}`; the most specific route matching a path answers it, whatever
the order they were added in; a path matched for another method is 405 with
`Allow`, any other 404. `http.json` and `http.json_body` make typed
endpoints of `#derive(Json)` types (a body that isn't one is 422). Alike in
the interpreter and natively, and served over loopback."""
import os
import tempfile
import unittest
import zlib

from tests.burn._native import (CAN_BUILD_NATIVE, SKIP_REASON, TEST_TARGET, Program, build_and_run_full,
                                run_source_both_now, selfhost_run, write_program)
from tests.burn.test_http import NO_SOCKETS, NO_SOCKETS_WHY

PROGRAM = """import std.http as http
import std.json as json
import std.fs as fs
from std.http import Request, Response

#derive(Json)
struct User {
    id: int,
    name: str,
}

#derive(Json)
struct NewUser {
    name: str,
}

fun get_user(req: Request) -> Result<User, Response> {
    let id = req.param_int("id").unwrap_or(0)
    if id == 7 { return Ok(User { id: 7, name: "ada" }) }
    return Err(http.json_error(404, f"no user {id}"))
}

fun create_user(req: Request, u: NewUser) -> Result<User, Response> {
    return Ok(User { id: 8, name: u.name })
}

fun text(body: str) -> (Request) -> Response {
    return (req: Request) => http.response(200, body)
}

fun tagged(next: (Request) -> Response) -> (Request) -> Response {
    return (req: Request) => next(req).with_header("X-Tag", "api")
}

fun show(r: Response) {
    let tag = r.header("X-Tag").unwrap_or("-")
    let allow = r.header("Allow").unwrap_or("-")
    print(f"{r.status} {r.text()} tag={tag} allow={allow}")
}

fun main() {
    var api = http.router("/api")
    api.get("/users/{id:int}", http.json(get_user))
    api.post("/users", http.json_body(create_user))
    api.get("/files/{rest:path}", (req: Request) => http.response(200, req.param("rest").unwrap_or("?")))
    // the parameter first: the literal segment still wins
    api.get("/items/{name}", (req: Request) => http.response(200, "item " + req.param("name").unwrap_or("?")))
    api.get("/items/new", text("the form"))
    api.wrap(tagged)
    var app = http.router("")
    app.get("/", (req: Request) => http.response(200, f"home {req.query_param("q").unwrap_or("-")}"))
    app.mount(api)
    let dir = match fs.make_temp_dir() {
        Ok(d) => d
        Err(e) => { panic("no temporary directory") }
    }
    let wrote = fs.write_to_file(dir + "/app.css", "body {}")
    app.static_files("/assets", dir)
    let h = app.handler()
    show(h(http.request("GET", "/?q=hello%20you")))
    show(h(http.request("GET", "/api/users/7")))
    show(h(http.request("GET", "/api/users/9")))
    show(h(http.request("GET", "/api/users/x")))
    show(h(http.request("DELETE", "/api/users/7")))
    show(h(http.request("POST", "/api/users").with_body("{\\"name\\": \\"bob\\"}")))
    show(h(http.request("POST", "/api/users").with_body("{\\"nom\\": 1}")))
    show(h(http.request("GET", "/api/files/a/b%20c.txt")))
    show(h(http.request("GET", "/api/items/new")))
    show(h(http.request("GET", "/api/items/lamp")))
    show(h(http.request("HEAD", "/api/items/lamp")))
    show(h(http.request("GET", "/nowhere")))
    let css = h(http.request("GET", "/assets/app.css"))
    print(f"{css.status} {css.text()} {css.header("Content-Type").unwrap_or("?")}")
    show(h(http.request("GET", "/assets/../secret")))
    show(h(http.request("GET", "/assets/missing.css")))
    let gone = fs.remove_dir_all(dir)
}
"""

WANT = """200 home hello you tag=- allow=-
200 {"id":7,"name":"ada"} tag=api allow=-
404 {"error":"no user 9"} tag=api allow=-
404 not found tag=api allow=-
405 method not allowed tag=api allow=GET
200 {"id":8,"name":"bob"} tag=api allow=-
422 {"error":"$.name: missing field"} tag=api allow=-
200 a/b c.txt tag=api allow=-
200 the form tag=api allow=-
200 item lamp tag=api allow=-
200 item lamp tag=api allow=-
404 not found tag=- allow=-
200 body {} text/css; charset=utf-8
404 not found tag=- allow=-
404 not found tag=- allow=-
"""

SERVED = """import std.http as http
import std.net as net
from std.http import Request

#main
async fun main() {
    var r = http.router("")
    r.get("/hello/{name}", (req: Request) => http.response(200, f"hello {req.param("name").unwrap_or("?")}"))
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("listen") }
    }
    let port = match l.local_addr() {
        Ok(a) => a.port
        Err(e) => { panic("local_addr") }
    }
    async let served = http.serve_n(l, 2, r.handler())
    for path in ["/hello/ada", "/nope"] {
        match await http.get_async(f"http://127.0.0.1:{port}{path}") {
            Ok(resp) => print(f"{resp.status} {resp.text()}")
            Err(e) => print(f"client: {e}")
        }
    }
    match await served {
        Ok(n) => print(f"served {n}")
        Err(e) => print(f"server: {e}")
    }
    let c = l.close()
}
"""


# std.http's static files (D260, MYLA-795): only regular files under the
# resolved root, no dot files by default, no symbolic links below the root,
# no FIFO (which would block the worker that opened it) or device; `..` taken
# off lexically, never past the root. argv[1] is the root, argv[2] a file
# outside it.
POLICY = """import std.http as http
import std.process as process
from std.http import Request, Response

fun main() {
    let root = process.args()[1]
    var app = http.router("")
    app.static_files("/assets", root)
    app.static_files("/dots", root, true)
    let h = app.handler()
    for p in ["/assets/app.css", "/assets/sub/a.txt", "/assets/sub/../app.css", "/assets//sub/./a.txt",
              "/assets/../outside.txt", "/assets/sub/../../outside.txt", "/assets/%2e%2e/outside.txt",
              "/assets/sub%2f..%2f..%2foutside.txt", "/assets/..%5coutside.txt", "/assets/.env",
              "/assets/.git/config", "/dots/.env", "/dots/.git/config", "/dots/../outside.txt",
              "/assets/leak.txt", "/assets/dirlink/outside.txt", "/assets/inlink.css", "/assets/fifo",
              "/assets/sub", "/assets/", "/assets/missing.css", "/assets/app.css%00.png"] {
        let r = h(http.request("GET", p))
        print(f"{p} {r.status} {r.text()}")
    }
}
"""

POLICY_WANT = """/assets/app.css 200 body {}
/assets/sub/a.txt 200 a
/assets/sub/../app.css 200 body {}
/assets//sub/./a.txt 200 a
/assets/../outside.txt 404 not found
/assets/sub/../../outside.txt 404 not found
/assets/%2e%2e/outside.txt 404 not found
/assets/sub%2f..%2f..%2foutside.txt 404 not found
/assets/..%5coutside.txt 404 not found
/assets/.env 404 not found
/assets/.git/config 404 not found
/dots/.env 200 SECRET=1
/dots/.git/config 200 [core]
/dots/../outside.txt 404 not found
/assets/leak.txt 404 not found
/assets/dirlink/outside.txt 404 not found
/assets/inlink.css 404 not found
/assets/fifo 404 not found
/assets/sub 404 not found
/assets/ 404 not found
/assets/missing.css 404 not found
/assets/app.css%00.png 404 not found
"""

# A file served over loopback is sent as it is read (D260): its bytes, its
# length for HEAD, and a FIFO in the directory answered 404 at once.
STREAMED = """import std.http as http
import std.net as net
import std.process as process
import std.checksum as checksum
from std.http import Request

#main
async fun main() {
    let root = process.args()[1]
    var r = http.router("")
    r.static_files("/s", root)
    var l = match net.listen(net.addr(net.loopback(), 0)) {
        Ok(l) => l
        Err(e) => { panic("listen") }
    }
    let port = match l.local_addr() {
        Ok(a) => a.port
        Err(e) => { panic("local_addr") }
    }
    async let served = http.serve_n(l, 4, r.handler())
    match await http.get_async(f"http://127.0.0.1:{port}/s/big.bin") {
        Ok(resp) => print(f"{resp.status} {resp.body.len()} {checksum.crc32(resp.body)} {resp.header("Content-Type").unwrap_or("?")}")
        Err(e) => print(f"client: {e}")
    }
    match await http.send_async(http.request("HEAD", f"http://127.0.0.1:{port}/s/big.bin")) {
        Ok(resp) => print(f"HEAD {resp.status} {resp.header("Content-Length").unwrap_or("?")} {resp.body.len()}")
        Err(e) => print(f"client: {e}")
    }
    for path in ["/s/fifo", "/s/small.txt"] {
        match await http.get_async(f"http://127.0.0.1:{port}{path}") {
            Ok(resp) => print(f"{resp.status} {resp.text()}")
            Err(e) => print(f"client: {e}")
        }
    }
    match await served {
        Ok(n) => print(f"served {n}")
        Err(e) => print(f"server: {e}")
    }
    let c = l.close()
}
"""

# M14: a pattern is matched as written, and a malformed one is a runtime
# error naming it when the route is added (D184).
PATTERNS = """import std.http as http
from std.http import Request, Response

fun say(s: str) -> (Request) -> Response {
    return (req: Request) => http.response(200, s)
}

fun main() {
    var app = http.router("")
    app.get("/users/{name}", say("a user"))
    app.get("/files/{p:path}", say("a file"))
    app.get("/items/{id:int}", say("an item by number"))
    let h = app.handler()
    for p in ["/files/a/b/meta", "/files", "/items/12", "/items/abc", "/users/ada"] {
        let r = h(http.request("GET", p))
        print(f"{p} {r.status} {r.text()}")
    }
    app.get("/files/{p:path}/meta", say("meta of a file"))
}
"""

PATTERNS_WANT = """/files/a/b/meta 200 a file
/files 200 a file
/items/12 200 an item by number
/items/abc 404 not found
/users/ada 200 a user
"""


def make_root(top: str) -> str:
    """The served directory of POLICY and STREAMED under `top`, beside a
    file and a directory outside it that links below it name (none for
    Windows, where Wine shows a Unix link as what it names: a link there is
    a reparse point, which `symlink_metadata` gives as one; their lines are
    404 for a name that isn't there)."""
    root = os.path.join(top, "www")
    os.makedirs(os.path.join(root, "sub"))
    os.makedirs(os.path.join(root, ".git"))
    os.makedirs(os.path.join(top, "out"))
    files = {"app.css": "body {}", "sub/a.txt": "a", ".env": "SECRET=1", ".git/config": "[core]", "small.txt": "small"}
    for name, text in files.items():
        with open(os.path.join(root, name), "w") as f:
            f.write(text)
    for path in (os.path.join(top, "outside.txt"), os.path.join(top, "out", "outside.txt")):
        with open(path, "w") as f:
            f.write("TOP SECRET")
    if TEST_TARGET != "x86_64-windows":
        os.symlink(os.path.join(top, "outside.txt"), os.path.join(root, "leak.txt"))
        os.symlink(os.path.join(top, "out"), os.path.join(root, "dirlink"))
        os.symlink("app.css", os.path.join(root, "inlink.css"))
    os.mkfifo(os.path.join(root, "fifo"))
    return root


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class StaticFiles(unittest.TestCase):
    def test_policy_in_the_interpreter_and_natively(self) -> None:
        with tempfile.TemporaryDirectory() as top:
            root = make_root(top)
            self.assertEqual(run_source_both_now(POLICY, [root]), (POLICY_WANT, "", 0))

    @unittest.skipIf(NO_SOCKETS, NO_SOCKETS_WHY)
    def test_streamed_over_loopback(self) -> None:
        with tempfile.TemporaryDirectory() as top:
            root = make_root(top)
            big = bytes((i * 7 + (i >> 9)) & 255 for i in range(3 * 1024 * 1024 + 123))
            with open(os.path.join(root, "big.bin"), "wb") as f:
                f.write(big)
            want = (f"200 {len(big)} {zlib.crc32(big)} application/octet-stream\n"
                    f"HEAD 200 {len(big)} 0\n404 not found\n200 small\nserved 4\n")
            self.assertEqual(run_source_both_now(STREAMED, [root]), (want, "", 0))


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Patterns(unittest.TestCase):
    def test_matched_as_written_and_malformed_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_program(tmp, PATTERNS)
            # the interpreter shows the panic's line of source after its message
            for out, err, code in (selfhost_run(path), build_and_run_full(Program(path))):
                self.assertEqual(out, PATTERNS_WANT)
                self.assertEqual(err.splitlines()[0], "runtime error: http: the route pattern '/files/{p:path}/meta': "
                                 "{p:path} isn't the last segment, and a path parameter takes the rest of the path")
                self.assertEqual(code, 1)


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Router(unittest.TestCase):
    def test_routing_in_the_interpreter_and_natively(self) -> None:
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    @unittest.skipIf(NO_SOCKETS, NO_SOCKETS_WHY)
    def test_served_over_loopback(self) -> None:
        self.assertEqual(run_source_both_now(SERVED), ("200 hello ada\n404 not found\nserved 2\n", "", 0))


if __name__ == "__main__":
    unittest.main()
