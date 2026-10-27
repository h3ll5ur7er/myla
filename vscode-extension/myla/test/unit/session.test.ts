// The debug adapter's protocol logic (src/debug/session.ts) against a fake
// gdb: what it asks gdb and what it tells the client. The real thing is
// tested in test/integration/adapter.test.ts.
import { test } from "node:test";
import assert from "node:assert/strict";
import type { DebugProtocol } from "@vscode/debugprotocol";
import { MylaDebugSession, shellQuote } from "../../src/debug/session.ts";
import { MiError, type MiResult, type MiTransport } from "../../src/debug/gdb.ts";
import { parseMiLine, type MiRecord } from "../../src/debug/mi.ts";

/** Answers commands with `answer`, which returns the result's text after `^done` or throws. */
class FakeGdb implements MiTransport {
  readonly sent: string[] = [];
  private recordListeners: ((r: MiRecord) => void)[] = [];
  private exitListeners: ((code: number | null) => void)[] = [];
  exited = false;
  private readonly answer: (command: string) => string;
  constructor(answer: (command: string) => string) {
    this.answer = answer;
  }
  async send(command: string): Promise<MiResult> {
    this.sent.push(command);
    const text = this.answer(command);
    if (text.startsWith("error:")) throw new MiError(text.slice(6));
    const r = parseMiLine(`^${text}`);
    if (r.kind !== "result") throw new Error(`bad fake answer ${text}`);
    return { resultClass: r.resultClass, results: r.results, console: "" };
  }
  onRecord(l: (r: MiRecord) => void): void {
    this.recordListeners.push(l);
  }
  onTrace(): void {}
  onExit(l: (code: number | null) => void): void {
    this.exitListeners.push(l);
  }
  kill(): void {
    this.exited = true;
    for (const l of this.exitListeners) l(null);
  }
  emit(line: string): void {
    for (const l of this.recordListeners) l(parseMiLine(line));
  }
}

class Harness {
  readonly messages: DebugProtocol.ProtocolMessage[] = [];
  readonly session: MylaDebugSession;
  private seq = 1;
  constructor(gdb?: FakeGdb) {
    this.session = new MylaDebugSession((m) => this.messages.push(m), {
      startGdb: gdb ? async () => gdb : undefined,
      pollInterval: 10,
    });
  }
  async request(command: string, args?: unknown): Promise<DebugProtocol.Response> {
    const seq = this.seq++;
    this.session.handleMessage({ seq, type: "request", command, arguments: args } as DebugProtocol.Request);
    for (let i = 0; i < 200; i++) {
      const r = this.messages.find((m) => m.type === "response" && (m as DebugProtocol.Response).request_seq === seq);
      if (r) return r as DebugProtocol.Response;
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    throw new Error(`no response to ${command}`);
  }
  async event(name: string): Promise<DebugProtocol.Event> {
    for (let i = 0; i < 200; i++) {
      const e = this.messages.find((m) => m.type === "event" && (m as DebugProtocol.Event).event === name);
      if (e) return e as DebugProtocol.Event;
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    throw new Error(`no ${name} event`);
  }
}

const bkpt = (n: number, line: number) =>
  `done,bkpt={number="${n}",type="breakpoint",file="x.my",fullname="/w/x.my",line="${line}"}`;

test("initialize announces breakpoints, evaluation and runtime errors", async () => {
  const h = new Harness();
  const r = await h.request("initialize", { adapterID: "myla" });
  const caps = r.body as DebugProtocol.Capabilities;
  assert.ok(caps.supportsConfigurationDoneRequest && caps.supportsConditionalBreakpoints && caps.supportsEvaluateForHovers);
  assert.deepEqual(
    caps.exceptionBreakpointFilters?.map((f) => [f.filter, f.default]),
    [["runtime-error", true]],
  );
});

test("a missing gdb fails the launch with what to do", async () => {
  const h = new Harness();
  const r = await h.request("launch", { program: "/bin/true", executable: "/bin/true", gdbPath: "/nonexistent/gdb" });
  assert.equal(r.success, false);
  assert.match(r.message ?? "", /Could not start gdb.*myla\.debug\.gdbPath/);
  h.session.dispose();
});

test("launch sets gdb up and redirects the program's output", async () => {
  const gdb = new FakeGdb(() => "done");
  const h = new Harness(gdb);
  const r = await h.request("launch", { program: "/w/x.my", executable: "/bin/true", args: ["a b", "it's"], cwd: "/tmp" });
  assert.ok(r.success, r.message);
  await h.event("initialized");
  assert.ok(gdb.sent.includes("-gdb-set mi-async on"));
  assert.ok(gdb.sent.includes('-file-exec-and-symbols "/bin/true"'));
  const args = gdb.sent.find((c) => c.includes("set args"))!;
  assert.match(args, /set args 'a b' 'it'\\\\''s' < \/dev\/null > \/\S+\/stdout 2> \/\S+\/stderr/);
  h.session.dispose();
});

test("a breakpoint falls back to the file's base name and reports gdb's line", async () => {
  const gdb = new FakeGdb((c) => {
    if (c.includes('--source "/w/x.my"')) return "error:No source file named /w/x.my.";
    if (c.startsWith('-break-insert -c "i == 5" --source "x.my" --line 4')) return bkpt(2, 6);
    return "done";
  });
  const h = new Harness(gdb);
  await h.request("launch", { program: "/w/x.my", executable: "/bin/true" });
  const r = await h.request("setBreakpoints", { source: { path: "/w/x.my" }, breakpoints: [{ line: 4, condition: "i == 5" }] });
  const [b] = (r.body as { breakpoints: DebugProtocol.Breakpoint[] }).breakpoints;
  assert.deepEqual([b.verified, b.line, b.id], [true, 6, 2]);
  // a second call replaces the first: gdb deletes breakpoint 2
  await h.request("setBreakpoints", { source: { path: "/w/x.my" }, breakpoints: [] });
  assert.ok(gdb.sent.includes("-break-delete 2"));
  h.session.dispose();
});

test("a line gdb can't place is unverified with its message", async () => {
  const gdb = new FakeGdb((c) => (c.startsWith("-break-insert") ? 'error:No line 99 in file "x.my".' : "done"));
  const h = new Harness(gdb);
  await h.request("launch", { program: "/w/x.my", executable: "/bin/true" });
  const r = await h.request("setBreakpoints", { source: { path: "/w/x.my" }, breakpoints: [{ line: 99 }] });
  const [b] = (r.body as { breakpoints: DebugProtocol.Breakpoint[] }).breakpoints;
  assert.equal(b.verified, false);
  assert.match(b.message ?? "", /No line 99/);
  h.session.dispose();
});

test("stops and the end of the program become events", async () => {
  const gdb = new FakeGdb((c) => (c === "-exec-run" ? "running" : c.startsWith("-break-insert") ? bkpt(1, 3) : "done"));
  const h = new Harness(gdb);
  await h.request("launch", { program: "/w/x.my", executable: "/bin/true" });
  await h.request("setBreakpoints", { source: { path: "/w/x.my" }, breakpoints: [{ line: 3 }] });
  await h.request("configurationDone");
  gdb.emit('*stopped,reason="breakpoint-hit",bkptno="1",frame={func="myla_main",line="3"},thread-id="1"');
  const stopped = await h.event("stopped");
  assert.deepEqual(stopped.body, { reason: "breakpoint", threadId: 1, allThreadsStopped: true, hitBreakpointIds: [1] });
  const cont = await h.request("continue", { threadId: 1 });
  assert.ok(cont.success);
  assert.ok(gdb.sent.includes("-exec-continue"));
  gdb.emit('*stopped,reason="exited",exit-code="012"');
  assert.deepEqual((await h.event("exited")).body, { exitCode: 10 });
  await h.event("terminated");
  h.session.dispose();
});

test("arguments are quoted for the shell gdb starts the program with", () => {
  assert.equal(shellQuote("plain-arg_1.txt"), "plain-arg_1.txt");
  assert.equal(shellQuote("a b"), "'a b'");
  assert.equal(shellQuote("it's"), "'it'\\''s'");
  assert.equal(shellQuote(""), "''");
  assert.equal(shellQuote("$HOME"), "'$HOME'");
});
