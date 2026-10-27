// The debug adapter against real gdb (MYLA-99): the adapter runs on stdio as
// VS Code's other clients would run it, debugs Myla programs the myla CLI
// builds with -g, and the tests check the DAP messages. Skipped without gdb or
// a Myla toolchain. Set DAP_TRANSCRIPT=<file> to keep every session's
// messages.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { DapClient, FIXTURES, markerLine, testCli } from "./dapClient.ts";

const hasGdb = spawnSync("gdb", ["--version"]).status === 0;
const cli = testCli();
const hasCli = fs.existsSync(cli) && (cli.endsWith(".py") ? spawnSync("python3", ["--version"]).status === 0 : true);
const hasBinutils = spawnSync("as", ["--version"]).status === 0 && spawnSync("ld", ["--version"]).status === 0;
const skip = !hasGdb ? "gdb isn't installed" : !hasCli ? `no myla CLI (${cli})` : !hasBinutils ? "needs as and ld" : false;

const DEBUGGEE = path.join(FIXTURES, "debuggee.my");
const SPIN = path.join(FIXTURES, "spin.my");
const clients: DapClient[] = [];

function client(): DapClient {
  const c = new DapClient();
  clients.push(c);
  return c;
}

after(async () => {
  for (const c of clients) await c.close();
  if (process.env.DAP_TRANSCRIPT) {
    const text = clients.map((c, i) => `# session ${i + 1}\n${c.transcript.join("\n")}\n`).join("\n");
    fs.writeFileSync(process.env.DAP_TRANSCRIPT, text);
  }
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Vars = any[];

async function variables(dap: DapClient, ref: number): Promise<Record<string, { value: string; ref: number; type?: string }>> {
  const body = await dap.ok("variables", { variablesReference: ref });
  const out: Record<string, { value: string; ref: number; type?: string }> = {};
  for (const v of body.variables as Vars) out[v.name] = { value: v.value, ref: v.variablesReference, type: v.type };
  return out;
}

async function topFrame(dap: DapClient, threadId: number) {
  const body = await dap.ok("stackTrace", { threadId, startFrame: 0, levels: 20 });
  return body.stackFrames;
}

test("breakpoints, stepping, the stack and variables", { skip }, async () => {
  const dap = client();
  const launched = await dap.start({ program: DEBUGGEE, cwd: FIXTURES });
  assert.ok(launched.success, launched.message);

  const locals = markerLine(DEBUGGEE, "locals");
  const callee = markerLine(DEBUGGEE, "callee");
  // a blank line moves to the next line with code
  let bps = await dap.ok("setBreakpoints", {
    source: { path: DEBUGGEE },
    breakpoints: [{ line: locals }, { line: callee - 3 }],
  });
  assert.equal(bps.breakpoints[0].verified, true);
  assert.equal(bps.breakpoints[0].line, locals);
  assert.equal(bps.breakpoints[1].verified, true);
  assert.ok(bps.breakpoints[1].line > callee - 3, `moved to ${bps.breakpoints[1].line}`);
  // replacing a file's breakpoints removes the others
  bps = await dap.ok("setBreakpoints", { source: { path: DEBUGGEE }, breakpoints: [{ line: locals }, { line: callee }] });
  assert.deepEqual(
    bps.breakpoints.map((b: { line: number }) => b.line),
    [locals, callee],
  );
  await dap.ok("setExceptionBreakpoints", { filters: ["runtime-error"] });
  await dap.ok("configurationDone");

  let stopped = await dap.event("stopped");
  assert.equal(stopped.reason, "breakpoint");
  const thread = stopped.threadId;
  let frames = await topFrame(dap, thread);
  assert.equal(frames[0].name, "main");
  assert.equal(frames[0].line, locals);
  assert.equal(frames[0].source.path, DEBUGGEE);

  const scopes = (await dap.ok("scopes", { frameId: frames[0].id })).scopes;
  assert.deepEqual(
    scopes.map((s: { name: string }) => s.name),
    ["Locals", "Arguments"],
  );
  const vars = await variables(dap, scopes[0].variablesReference);
  assert.equal(vars.origin.value, "Point {x: 1, y: 2}");
  assert.equal(vars.name.value, '"héllo"');
  assert.equal(vars.name.ref, 0);
  assert.equal(vars.xs.value, "[1, -2, 3]");
  assert.equal(vars.s.value, "Shape::Circle(Point {x: 1, y: 2}, 5)");
  assert.equal(vars.t.value, "(7, true)");

  const origin = await variables(dap, vars.origin.ref);
  assert.deepEqual([origin.x.value, origin.y.value], ["1", "2"]);
  const xs = await variables(dap, vars.xs.ref);
  assert.deepEqual(Object.keys(xs), ["[0]", "[1]", "[2]"]);
  assert.equal(xs["[1]"].value, "-2");
  // an enum shows its active variant's fields
  const s = await variables(dap, vars.s.ref);
  assert.deepEqual(Object.keys(s), ["0", "1"]);
  assert.equal(s["0"].value, "Point {x: 1, y: 2}");
  assert.equal(s["1"].value, "5");
  const t = await variables(dap, vars.t.ref);
  assert.deepEqual([t["0"].value, t["1"].value], ["7", "true"]);
  // heap values inside a struct show as values, not as cell pointers
  const bag = await variables(dap, vars.bag.ref);
  assert.equal(bag.items.value, "[4, 5]");
  assert.equal(bag.label.value, '"two"');
  const items = await variables(dap, bag.items.ref);
  assert.deepEqual(Object.values(items).map((v) => v.value), ["4", "5"]);

  // evaluate in the debug console and on hover, and a raw gdb command
  let ev = await dap.ok("evaluate", { expression: "xs[1] * 10", frameId: frames[0].id, context: "repl" });
  assert.equal(ev.result, "-20");
  ev = await dap.ok("evaluate", { expression: "origin", frameId: frames[0].id, context: "hover" });
  assert.equal(ev.result, "Point {x: 1, y: 2}");
  assert.ok(ev.variablesReference > 0);
  ev = await dap.ok("evaluate", { expression: "bag.label", frameId: frames[0].id, context: "watch" });
  assert.equal(ev.result, '"two"');
  ev = await dap.ok("evaluate", { expression: "-exec print 6 * 7", frameId: frames[0].id, context: "repl" });
  assert.match(ev.result, /= 42/);
  const bad = await dap.request("evaluate", { expression: "nope + 1", frameId: frames[0].id, context: "repl" });
  assert.equal(bad.success, false);
  assert.match(bad.message ?? "", /nope/);

  // next, then change a variable the program prints later
  await dap.ok("next", { threadId: thread });
  stopped = await dap.event("stopped");
  assert.equal(stopped.reason, "step");
  frames = await topFrame(dap, thread);
  assert.equal(frames[0].line, markerLine(DEBUGGEE, "call"));
  const scopes2 = (await dap.ok("scopes", { frameId: frames[0].id })).scopes;
  await variables(dap, scopes2[0].variablesReference);
  const set = await dap.ok("setVariable", { variablesReference: scopes2[0].variablesReference, name: "total", value: "41" });
  assert.equal(set.value, "41");

  // step in: the callee, with its arguments and the caller below it
  await dap.ok("stepIn", { threadId: thread });
  await dap.event("stopped");
  frames = await topFrame(dap, thread);
  assert.equal(frames[0].name, "shifted_x");
  assert.equal(frames[0].line, callee);
  assert.equal(frames[1].name, "main");
  assert.equal(frames[1].line, markerLine(DEBUGGEE, "call"));
  assert.equal(frames.at(-1).presentationHint, "subtle");
  const calleeScopes = (await dap.ok("scopes", { frameId: frames[0].id })).scopes;
  const args = await variables(dap, calleeScopes[1].variablesReference);
  assert.equal(args.p.value, "Point {x: 1, y: 2}");
  assert.equal(args.dx.value, "3");
  // a caller's frame has its own variables
  const callerScopes = (await dap.ok("scopes", { frameId: frames[1].id })).scopes;
  assert.equal((await variables(dap, callerScopes[0].variablesReference)).total.value, "41");

  // step out, then run to the end: the program prints the changed total
  await dap.ok("stepOut", { threadId: thread });
  stopped = await dap.event("stopped");
  assert.equal(stopped.reason, "step");
  frames = await topFrame(dap, thread);
  assert.equal(frames[0].name, "main");
  await dap.ok("continue", { threadId: thread });
  const exited = await dap.event("exited");
  assert.equal(exited.exitCode, 0);
  await dap.event("terminated");
  assert.equal(dap.output("stdout"), "45\nhéllo\n5\n5\n");
});

test("a runtime error stops where it happens", { skip }, async () => {
  const dap = client();
  assert.ok((await dap.start({ program: DEBUGGEE, args: ["panic"] })).success);
  await dap.ok("setBreakpoints", { source: { path: DEBUGGEE }, breakpoints: [] });
  await dap.ok("setExceptionBreakpoints", { filters: ["runtime-error"] });
  await dap.ok("configurationDone");
  const stopped = await dap.event("stopped");
  assert.equal(stopped.reason, "exception");
  assert.equal(stopped.text, "division by zero");
  const info = await dap.ok("exceptionInfo", { threadId: stopped.threadId });
  assert.equal(info.description, "division by zero");
  assert.match(info.details.stackTrace, new RegExp(`debuggee\\.my:${markerLine(DEBUGGEE, "divide")}:\\d+`));
  const frames = await topFrame(dap, stopped.threadId);
  // the runtime's frame has no source; the Myla frame below it is where it failed
  assert.equal(frames[0].name, "__panic");
  assert.equal(frames[0].source, undefined);
  assert.equal(frames[0].presentationHint, "subtle");
  assert.equal(frames[1].name, "ratio");
  assert.equal(frames[1].line, markerLine(DEBUGGEE, "divide"));
  const scopes = (await dap.ok("scopes", { frameId: frames[1].id })).scopes;
  const args = await variables(dap, scopes[1].variablesReference);
  assert.deepEqual([args.a.value, args.b.value], ["7", "0"]);
  await dap.ok("continue", { threadId: stopped.threadId });
  assert.equal((await dap.event("exited")).exitCode, 1);
  await dap.event("terminated");
  assert.match(dap.output("stderr"), /runtime error: division by zero\n {2}--> .*debuggee\.my:\d+:\d+\n/);
});

test("stop on entry, a function breakpoint and the exit code", { skip }, async () => {
  const dap = client();
  assert.ok((await dap.start({ program: DEBUGGEE, args: ["exit"], stopOnEntry: true })).success);
  const fbps = await dap.ok("setFunctionBreakpoints", { breakpoints: [{ name: "shifted_x" }, { name: "nope" }] });
  assert.deepEqual(
    fbps.breakpoints.map((b: { verified: boolean }) => b.verified),
    [true, false],
  );
  await dap.ok("configurationDone");
  let stopped = await dap.event("stopped");
  assert.equal(stopped.reason, "entry");
  let frames = await topFrame(dap, stopped.threadId);
  assert.equal(frames[0].name, "main");
  await dap.ok("continue", { threadId: stopped.threadId });
  stopped = await dap.event("stopped");
  assert.equal(stopped.reason, "function breakpoint");
  frames = await topFrame(dap, stopped.threadId);
  assert.equal(frames[0].name, "shifted_x");
  await dap.ok("continue", { threadId: stopped.threadId });
  assert.equal((await dap.event("exited")).exitCode, 3);
  await dap.event("terminated");
});

test("a conditional breakpoint, pause and terminate", { skip }, async () => {
  const dap = client();
  assert.ok((await dap.start({ program: SPIN })).success);
  const line = markerLine(SPIN, "loop");
  const bps = await dap.ok("setBreakpoints", { source: { path: SPIN }, breakpoints: [{ line, condition: "i == 5" }] });
  assert.equal(bps.breakpoints[0].verified, true);
  await dap.ok("configurationDone");
  let stopped = await dap.event("stopped");
  assert.equal(stopped.reason, "breakpoint");
  const frames = await topFrame(dap, stopped.threadId);
  const ev = await dap.ok("evaluate", { expression: "i", frameId: frames[0].id, context: "repl" });
  assert.equal(ev.result, "5");
  // remove it, run; a breakpoint set while the program runs stops it
  await dap.ok("setBreakpoints", { source: { path: SPIN }, breakpoints: [] });
  await dap.ok("continue", { threadId: stopped.threadId });
  await new Promise((r) => setTimeout(r, 200));
  await dap.ok("setBreakpoints", { source: { path: SPIN }, breakpoints: [{ line }] });
  stopped = await dap.event("stopped");
  assert.equal(stopped.reason, "breakpoint");
  // remove it again, run, pause
  await dap.ok("setBreakpoints", { source: { path: SPIN }, breakpoints: [] });
  await dap.ok("continue", { threadId: stopped.threadId });
  await new Promise((r) => setTimeout(r, 300));
  await dap.ok("pause", { threadId: stopped.threadId });
  stopped = await dap.event("stopped");
  assert.equal(stopped.reason, "pause");
  await dap.ok("terminate", {});
  await dap.event("terminated");
});

test("a program that doesn't compile fails to launch with the compiler's message", { skip }, async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "myla-dap-"));
  const bad = path.join(dir, "bad.my");
  fs.writeFileSync(bad, 'fun main() {\n    let x: int = "a"\n}\n');
  const dap = client();
  const r = await dap.start({ program: bad });
  assert.equal(r.success, false);
  assert.match(r.message ?? "", /Build failed: type error: cannot assign value of type 'str'.*bad\.my:2/);
  assert.match(dap.output("stderr"), /--> .*bad\.my:2:5/);
  fs.rmSync(dir, { recursive: true, force: true });
});

test("run without debugging", { skip }, async () => {
  const dap = client();
  assert.ok((await dap.start({ program: DEBUGGEE, args: ["exit"], noDebug: true })).success);
  await dap.ok("configurationDone");
  assert.equal((await dap.event("exited")).exitCode, 3);
  await dap.event("terminated");
  assert.equal(dap.output("stdout"), "4\nhéllo\n");
});

test("a project is built by its own `myla build` and debugged (MYLA-94)", { skip }, async () => {
  // a project with a path dependency: only the project build passes the --package flags it needs
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "myla-dap-"));
  const put = (rel: string, text: string) => {
    fs.mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true });
    fs.writeFileSync(path.join(dir, rel), text);
  };
  put("geo/myla.toml", '[package]\nname = "geo"\nversion = "1"\n');
  put("geo/src/geo.my", "pub fun area(w: int, h: int) -> int {\n    let a = w * h\n    return a\n}\n");
  put("app/myla.toml", '[package]\nname = "app"\nversion = "1"\n\n[dependencies]\ngeo = { path = "../geo" }\n');
  put("app/src/main.my", "import geo\n\nfun main() {\n    print(geo.area(3, 4))\n}\n");
  const geoFile = path.join(dir, "geo", "src", "geo.my");
  const dap = client();
  const r = await dap.start({ program: path.join(dir, "app") });
  if (cli.endsWith(".py")) {
    // the Python CLI has no project commands (D71)
    assert.equal(r.success, false);
    assert.match(r.message ?? "", /needs the self-hosted CLI/);
  } else {
    assert.ok(r.success, r.message);
    const bp = await dap.ok("setBreakpoints", { source: { path: geoFile }, breakpoints: [{ line: 3 }] });
    assert.equal(bp.breakpoints[0].verified, true);
    await dap.ok("configurationDone");
    const stopped = await dap.event("stopped");
    assert.equal(stopped.reason, "breakpoint");
    const frames = await topFrame(dap, stopped.threadId);
    assert.equal(path.basename(frames[0].source.path), "geo.my");
    assert.equal(frames[0].line, 3);
    const scopes = (await dap.ok("scopes", { frameId: frames[0].id })).scopes;
    const locals = await variables(dap, scopes[0].variablesReference);
    assert.equal(locals.a.value, "12");
    await dap.ok("continue", { threadId: stopped.threadId });
    assert.equal((await dap.event("exited")).exitCode, 0);
    await dap.event("terminated");
    assert.equal(dap.output("stdout"), "12\n");
    assert.ok(fs.existsSync(path.join(dir, "app", "build", "app")));
  }
  fs.rmSync(dir, { recursive: true, force: true });
});
