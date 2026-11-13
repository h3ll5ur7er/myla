---
id: MYLA-613
title: std.http Router for typed web APIs
type: feature
status: todo
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

- [ ] The API proposed with examples in this task and accepted by the owner (method helpers `r.get(path, h)`, `r.post`, …, `r.mount(path, router)`, `r.wrap(middleware)`, `http.json`, `http.static_files`), and recorded as a decision
- [ ] Tests first: a burn test that serves a router on loopback and checks routing, typed parameters, JSON in and out, 404/405/422, a sub-router, a middleware, a static mount; interpreted and natively
- [ ] `lib/std/http.my` (or a `std.http` submodule if it grows), `#test` cases on every value-returning function
- [ ] An example in `examples/` (a small JSON API), registered in the example tests
- [ ] Docs: [[Language/Standard-library/Http]], the skill's `reference/stdlib.md`
- [ ] Later, with custom attributes: the `#route(…)` sugar as a desugaring into this API (its own task)
