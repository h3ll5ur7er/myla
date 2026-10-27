// The GDB/MI output parser and command quoting (src/debug/mi.ts), on records
// gdb 15 printed for a Myla program.
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseMiLine, miQuote, miString, miTuple, miList } from "../../src/debug/mi.ts";

test("a result record with a token, tuples and a list of results", () => {
  const r = parseMiLine(
    '12^done,stack=[frame={level="0",addr="0x4036f2",func="myla_shifted_x",file="d.my",fullname="/w/d.my",line="19"},frame={level="1",func="_start"}]',
  );
  assert.equal(r.kind, "result");
  if (r.kind !== "result") return;
  assert.equal(r.token, 12);
  assert.equal(r.resultClass, "done");
  const frames = miList(r.results.stack);
  assert.equal(frames.length, 2);
  assert.equal(miString(miTuple(frames[0]).func), "myla_shifted_x");
  assert.equal(miString(miTuple(frames[0]).line), "19");
  assert.equal(miTuple(frames[1]).file, undefined);
});

test("an async exec record without a token", () => {
  const r = parseMiLine(
    '*stopped,reason="breakpoint-hit",disp="keep",bkptno="1",frame={addr="0x403527",func="myla_main",args=[]},thread-id="1",stopped-threads="all"',
  );
  assert.equal(r.kind, "exec");
  if (r.kind !== "exec") return;
  assert.equal(r.token, undefined);
  assert.equal(r.asyncClass, "stopped");
  assert.equal(miString(r.results.reason), "breakpoint-hit");
  assert.deepEqual(miList(miTuple(r.results.frame).args), []);
  assert.equal(miString(r.results["thread-id"]), "1");
});

test("notify and status records", () => {
  const n = parseMiLine('=thread-group-exited,id="i1",exit-code="03"');
  assert.equal(n.kind, "notify");
  if (n.kind === "notify") assert.equal(miString(n.results["exit-code"]), "03");
  const s = parseMiLine("+download,{section=\".text\"}");
  assert.equal(s.kind, "status");
});

test("stream records decode C escapes", () => {
  const c = parseMiLine('~"Breakpoint 1, myla_main () at d.my:39\\n"');
  assert.deepEqual(c, { kind: "console", text: "Breakpoint 1, myla_main () at d.my:39\n" });
  const l = parseMiLine('&"warning: \\"x\\"\\tdone\\\\\\n"');
  assert.deepEqual(l, { kind: "log", text: 'warning: "x"\tdone\\\n' });
  assert.deepEqual(parseMiLine('@"out"'), { kind: "target", text: "out" });
});

test("octal escapes are UTF-8 bytes", () => {
  const r = parseMiLine('^done,value="\\"h\\303\\251llo \\360\\237\\230\\200\\""');
  assert.equal(r.kind, "result");
  if (r.kind === "result") assert.equal(miString(r.results.value), '"héllo 😀"');
});

test("a list of values and an empty tuple", () => {
  const r = parseMiLine('^done,groups=["i1","i2"],empty={},nested=[[],{a="1"}]');
  assert.equal(r.kind, "result");
  if (r.kind !== "result") return;
  assert.deepEqual(miList(r.results.groups).map(miString), ["i1", "i2"]);
  assert.deepEqual(miTuple(r.results.empty), {});
  assert.equal(miList(r.results.nested).length, 2);
});

test("an error record", () => {
  const r = parseMiLine('7^error,msg="No symbol \\"nope\\" in current context."');
  assert.equal(r.kind, "result");
  if (r.kind !== "result") return;
  assert.equal(r.token, 7);
  assert.equal(r.resultClass, "error");
  assert.equal(miString(r.results.msg), 'No symbol "nope" in current context.');
});

test("the prompt, blank lines and other text", () => {
  assert.equal(parseMiLine("(gdb) ").kind, "prompt");
  assert.equal(parseMiLine("(gdb)").kind, "prompt");
  assert.deepEqual(parseMiLine("hello from the program"), { kind: "other", text: "hello from the program" });
  assert.deepEqual(parseMiLine("^done,value=\"unterminated"), { kind: "other", text: "^done,value=\"unterminated" });
});

test("CRLF line ends are ignored", () => {
  const r = parseMiLine("3^running\r");
  assert.equal(r.kind, "result");
  if (r.kind === "result") assert.equal(r.resultClass, "running");
});

test("miQuote makes a C string gdb reads back", () => {
  assert.equal(miQuote("plain"), '"plain"');
  assert.equal(miQuote('a "b" \\ c\nd'), '"a \\"b\\" \\\\ c\\nd"');
  // round trip through the parser
  const text = 'set args \'it\'\'s\' > "/tmp/a b/out"';
  const r = parseMiLine("^done,value=" + miQuote(text));
  assert.equal(r.kind, "result");
  if (r.kind === "result") assert.equal(miString(r.results.value), text);
});
