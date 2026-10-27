// Building a program for the debugger and reading the compiler's diagnostics
// (src/build.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseDiagnostics, buildCommand, debugTarget, debugOutputPath } from "../../src/build.ts";

test("a type error with its range", () => {
  const out = [
    "type error: cannot assign value of type 'str' to binding of type 'int32'",
    "  --> /w/bad.my:2:5",
    "  |",
    '2 |     let x: int = "a"',
    "  |     ^^^^^^^^^^^^^^^^",
    "",
  ].join("\n");
  assert.deepEqual(parseDiagnostics(out), [
    {
      file: "/w/bad.my",
      line: 2,
      column: 5,
      endColumn: 21,
      severity: "error",
      message: "type error: cannot assign value of type 'str' to binding of type 'int32'",
    },
  ]);
});

test("several diagnostics, relative paths, and a runtime error without a snippet", () => {
  const out = [
    "parse error: expected '}'",
    "  --> src/a.my:10:1",
    "runtime error: division by zero",
    "  --> b.my:5:14",
    "myla: linker failed",
  ].join("\n");
  const ds = parseDiagnostics(out, "/proj");
  assert.deepEqual(
    ds.map((d) => [d.file, d.line, d.column, d.endColumn, d.message]),
    [
      ["/proj/src/a.my", 10, 1, undefined, "parse error: expected '}'"],
      ["/proj/b.my", 5, 14, undefined, "runtime error: division by zero"],
    ],
  );
});

test("a message without a position is not a diagnostic", () => {
  assert.deepEqual(parseDiagnostics("error: cannot read nope.my\n"), []);
});

test("the build command line", () => {
  const cli = { command: "python3", args: ["/r/myla.py"] };
  assert.deepEqual(buildCommand(cli, "/w/a.my", "/tmp/out/a", true), {
    command: "python3",
    args: ["/r/myla.py", "build", "/w/a.my", "-o", "/tmp/out/a", "-g"],
  });
  assert.deepEqual(buildCommand({ command: "/r/build/myla", args: [] }, "/w/a.my", "/o/a", false).args, [
    "build",
    "/w/a.my",
    "-o",
    "/o/a",
  ]);
});

test("what a launch configuration's program names", () => {
  const files = new Set(["/w/a.my", "/w/app/myla.toml", "/w/app/src/main.my", "/w/bin/prog"]);
  const dirs = new Set(["/w/app"]);
  const fs = { isFile: (p: string) => files.has(p), isDirectory: (p: string) => dirs.has(p) };
  assert.deepEqual(debugTarget("/w/a.my", fs), { kind: "file", file: "/w/a.my" });
  assert.deepEqual(debugTarget("/w/bin/prog", fs), { kind: "binary", path: "/w/bin/prog" });
  // the project hook: a project directory or its manifest debugs src/main.my
  assert.deepEqual(debugTarget("/w/app", fs), { kind: "project", root: "/w/app", main: "/w/app/src/main.my" });
  assert.deepEqual(debugTarget("/w/app/myla.toml", fs), { kind: "project", root: "/w/app", main: "/w/app/src/main.my" });
  const missing = debugTarget("/w/nope.my", fs);
  assert.equal(missing.kind, "missing");
});

test("debug builds of different files don't collide", () => {
  const a = debugOutputPath("/tmp/d", "/w/x/main.my");
  const b = debugOutputPath("/tmp/d", "/w/y/main.my");
  assert.notEqual(a, b);
  assert.match(a, /^\/tmp\/d\/main-[0-9a-f]{8}$/);
  assert.equal(a, debugOutputPath("/tmp/d", "/w/x/main.my"));
});
