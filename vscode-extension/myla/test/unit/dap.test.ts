// The Debug Adapter Protocol's base protocol: Content-Length framing
// (src/debug/dap.ts).
import { test } from "node:test";
import assert from "node:assert/strict";
import { MessageReader, encodeMessage } from "../../src/debug/dap.ts";

test("a message round-trips through the framing", () => {
  const got: unknown[] = [];
  const reader = new MessageReader((m) => got.push(m));
  const msg = { seq: 1, type: "request", command: "initialize", arguments: { adapterID: "myla" } };
  reader.push(encodeMessage(msg));
  assert.deepEqual(got, [msg]);
});

test("Content-Length counts bytes, not characters", () => {
  const msg = { seq: 2, type: "event", event: "output", body: { output: "héllo 😀\n" } };
  const frame = encodeMessage(msg);
  const header = frame.toString("latin1").split("\r\n")[0];
  const body = Buffer.from(JSON.stringify(msg), "utf8");
  assert.equal(header, `Content-Length: ${body.length}`);
  assert.notEqual(body.length, JSON.stringify(msg).length);
});

test("messages split across chunks and several in one chunk", () => {
  const got: unknown[] = [];
  const reader = new MessageReader((m) => got.push(m));
  const a = encodeMessage({ seq: 1, type: "request", command: "threads" });
  const b = encodeMessage({ seq: 2, type: "request", command: "next", arguments: { threadId: 1, text: "é" } });
  const all = Buffer.concat([a, b]);
  // byte by byte, so a split falls inside the header, the separator and a
  // multi-byte character
  for (let i = 0; i < all.length; i++) reader.push(all.subarray(i, i + 1));
  assert.equal(got.length, 2);
  reader.push(Buffer.concat([a, b]));
  assert.equal(got.length, 4);
  assert.deepEqual(got[3], { seq: 2, type: "request", command: "next", arguments: { threadId: 1, text: "é" } });
});

test("other headers are allowed and a bad body is reported", () => {
  const got: unknown[] = [];
  const errors: string[] = [];
  const reader = new MessageReader((m) => got.push(m), (e) => errors.push(e.message));
  reader.push(Buffer.from('Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}', "utf8"));
  assert.deepEqual(got, [{}]);
  reader.push(Buffer.from("Content-Length: 3\r\n\r\n{x}", "utf8"));
  assert.equal(errors.length, 1);
  // the reader goes on after a bad message
  reader.push(encodeMessage({ seq: 3 }));
  assert.deepEqual(got[1], { seq: 3 });
});
