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
import unittest

from tests.burn._native import CAN_BUILD_NATIVE, SKIP_REASON, run_source_both_now
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


@unittest.skipUnless(CAN_BUILD_NATIVE, SKIP_REASON)
class Router(unittest.TestCase):
    def test_routing_in_the_interpreter_and_natively(self) -> None:
        self.assertEqual(run_source_both_now(PROGRAM), (WANT, "", 0))

    @unittest.skipIf(NO_SOCKETS, NO_SOCKETS_WHY)
    def test_served_over_loopback(self) -> None:
        self.assertEqual(run_source_both_now(SERVED), ("200 hello ada\n404 not found\nserved 2\n", "", 0))


if __name__ == "__main__":
    unittest.main()
