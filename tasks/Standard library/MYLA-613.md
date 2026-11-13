---
id: MYLA-613
title: std.http Router for typed web APIs
type: feature
status: review
priority: high
labels: [stdlib, http]
---
A router in `std.http` for easy, typed web APIs in the spirit of Python's FastAPI, built only from what the language has today, so that a later attribute such as `#route(GET, "/api/user/{id:int}", UserDTO)` can desugar into it unchanged.

## The owner's design (2026-11-13)

- A **route** has a method, a base path (a pattern) and a handler `(Request) -> Response`.
- A **router** has a base path and a map of routes, and is itself a handler: `(Request) -> Response`. So a router holds routes and sub-routers alike, and the same shape covers static file mounts (`http.static_files("/assets", dir)`) and middleware (a function from handler to handler: logging, CORS, authentication, timing).
- Typed endpoints: a `#derive(Json)` DTO in and out, path parameters typed by their pattern (`{id:int}`, `{name}`, `{rest:path}`), query parameters by name.

## Fitting it to the language (what the code read found)

- No trait objects and no method values, so the router stores handlers as function values; `r.handler()` returns a closure over a copy of the router (closures capture by value, D93). A router is built first, then served; it can't be changed while serving.
- Generic functions can't be values, but a generic call can return a closure: `http.json<UserIn, UserOut>((u: UserIn) => …)` makes a `(Request) -> Response` that decodes the body with `json.decode<UserIn>`, answers 422 with the decoder's error, and encodes the result.
- Path parameters reach the handler through the request (`req.param("id")`, `req.param_int("id")`, `Result`s so a bad value answers 400/404), since a closure can't take a variable number of typed arguments.
- Matching order: a map keeps insertion order (D105), but a router should prefer static segments to parameters (`/users/me` before `/users/{id}`) whatever the order of registration; method mismatch answers 405 with `Allow`, no match 404.
- `serve`/`serve_n` take a plain `(Request) -> Response` and `serve_with` an async one (`async (Request) -> Response`): decide whether a router has an async variant too, or handlers stay synchronous and blocking work moves to tasks.

## Steps

- [x] The API as the owner designed it (2026-11-13, "go on with the router"), recorded as D202: `r.get(path, h)`, `r.post`, …, `r.mount(sub)` (the sub-router's own base), `r.static_files(prefix, dir)`, `r.wrap(middleware)`, `http.json`, `http.json_body`
- [x] Tests first: a burn test that serves a router on loopback and checks routing, typed parameters, JSON in and out, 404/405/422, a sub-router, a middleware, a static mount; interpreted and natively
- [x] `lib/std/http.my` (or a `std.http` submodule if it grows), `#test` cases on every value-returning function
- [x] An example in `examples/` (a small JSON API), registered in the example tests
- [x] Docs: [[Language/Standard-library/Http]], the skill's `reference/stdlib.md`
- [ ] Later, with custom attributes: the `#route(…)` sugar as a desugaring into this API (its own task)

## What was built

- `Router { base, routes: [str: Route], wraps }`; routes keyed by `"METHOD pattern"`, so adding the same method and pattern replaces the route. `mount(sub)` stores `sub.handler()` (its middleware included) as a route that matches `sub`'s base and everything below, and hands the rest of the path on in the reserved parameter `%rest`; `static_files` is a `GET` route `prefix/{%file:path}`.
- Specificity, not registration order: literal 3, `{name:int}` 2, `{name}` 1, `{name:path}` 0, ties to the first added. 405 with `Allow` when only other methods match; `GET` routes answer `HEAD`.
- `Request` gained `params: [(str, str)]` and `param`, `param_int`, `query_param`. `http.json(f)` / `http.json_body(f)` for `#derive(Json)` endpoints; a body that doesn't decode is 422 `{"error": "$.name: missing field"}` (the `JsonError`'s `Format`, so the field is named). `json_response`, `json_error`, `content_type`.
- `examples/book_api.my`: a read-only book API; its logic is plain functions with `#test` cases (`find`, `search_for`, `add_book`), the routes closures over them, called directly through the router's handler. 7/7 cases pass interpreted and `--native`.

## Evidence

- `tests/burn/test_router.py` before the change: `module error: module 'std.http' does not export 'json_error'` (and `'router'`); after: 2 tests OK (routing alike interpreted and native; loopback `serve_n` with `get_async`).
- `build/myla test lib/std/http.my --stdlib lib`: 241/241 (225 before, 16 new: `split_path`, `segs_start`, `param_of`, `pattern_score`, `match_pattern`, `all_digits`, `content_type`); `--native` 241/241.
- `tests.burn.test_http`: 12 tests OK (1 skipped, as before). `test_examples_run`, `test_examples_compile`: OK with `book_api.my`.
- `scripts/test-target.py wasm32-wasi test_router`: passed (loopback skipped: no sockets). aarch64 needs `qemu-aarch64`, which this container lacks: CI runs it.

## Follow-ups

- Async handlers: `serve`/`serve_n` take sync handlers, and closures can't be async yet, so a router can't await (a database). Needs async closures, or a router of `async (Request) -> Response` built on `serve_with`.
- State between requests: handlers are values with copied captures (D89, D93), so a `POST` can't store anything except through the file system or a process; shared state needs an actor reachable from an async handler.
- The `#route(…)` sugar once custom attributes exist (last step above).
