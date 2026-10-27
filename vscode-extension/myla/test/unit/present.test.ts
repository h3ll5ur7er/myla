// How the adapter presents what gdb says in Myla's terms
// (src/debug/present.ts): function names, stop reasons, values and the
// expressions that reach a variable's children.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  functionName,
  isRuntimeFrame,
  stopReason,
  parseExitCode,
  isExpandable,
  childPath,
  displayChildName,
  shapeOf,
  quoteMylaString,
  readLittleEndian,
} from "../../src/debug/present.ts";

test("function names as Myla writes them", () => {
  assert.equal(functionName("myla_main"), "main");
  assert.equal(functionName("myla_Point.len"), "Point.len");
  assert.equal(functionName("myla_geometry$area"), "geometry.area");
  assert.equal(functionName("myla_checker$Checker.check_stmt"), "checker.Checker.check_stmt");
  assert.equal(functionName("myla___lambda_3"), "<lambda 3>");
  assert.equal(functionName("myla_main__lam0"), "main.<lambda 0>");
  assert.equal(functionName("__panic"), "__panic");
  assert.equal(functionName(""), "??");
});

test("runtime frames have no Myla source", () => {
  assert.ok(isRuntimeFrame("__panic"));
  assert.ok(isRuntimeFrame("_start"));
  assert.ok(!isRuntimeFrame("myla_main"));
});

test("stop reasons", () => {
  const ctx = { panicBreakpoint: 4, entryBreakpoint: 9, functionBreakpoints: new Set([5]), pauseRequested: false };
  assert.deepEqual(stopReason({ reason: "breakpoint-hit", bkptno: "1" }, ctx), { reason: "breakpoint", breakpoint: 1 });
  assert.deepEqual(stopReason({ reason: "breakpoint-hit", bkptno: "4" }, ctx), { reason: "exception" });
  assert.deepEqual(stopReason({ reason: "breakpoint-hit", bkptno: "9" }, ctx), { reason: "entry" });
  assert.deepEqual(stopReason({ reason: "breakpoint-hit", bkptno: "5" }, ctx), {
    reason: "function breakpoint",
    breakpoint: 5,
  });
  assert.deepEqual(stopReason({ reason: "end-stepping-range" }, ctx), { reason: "step" });
  assert.deepEqual(stopReason({ reason: "function-finished" }, ctx), { reason: "step" });
  assert.deepEqual(stopReason({ reason: "signal-received", "signal-name": "SIGINT" }, ctx), { reason: "pause" });
  assert.deepEqual(
    stopReason({ reason: "signal-received", "signal-name": "SIGSEGV", "signal-meaning": "Segmentation fault" }, ctx),
    { reason: "exception", description: "SIGSEGV: Segmentation fault" },
  );
  assert.deepEqual(stopReason({ reason: "exited-normally" }, ctx), { exited: 0 });
  assert.deepEqual(stopReason({ reason: "exited", "exit-code": "03" }, ctx), { exited: 3 });
  assert.deepEqual(stopReason({ reason: "exited-signalled", "signal-name": "SIGKILL" }, ctx), {
    exited: 137,
    description: "SIGKILL",
  });
});

test("gdb's exit codes are octal", () => {
  assert.equal(parseExitCode("01"), 1);
  assert.equal(parseExitCode("012"), 10);
  assert.equal(parseExitCode(""), 0);
});

test("which values expand", () => {
  for (const type of ["int32", "uint8", "float64", "bool", "char", "&str"]) assert.ok(!isExpandable(type, "1"), type);
  for (const type of ["Point", "(int32, bool)", "[int32; 3]", "*mut [int32]", "Shape", "*mut [str: int32]"]) {
    assert.ok(isExpandable(type, "{...}"), type);
  }
  // a heap string is shown as its text
  assert.ok(!isExpandable("*mut str", "0x4051b0"));
  // a variant without fields has nothing to show
  assert.ok(!isExpandable("Option<int32>", "Option<int32>::None"));
  assert.ok(isExpandable("Option<int32>", "Option<int32>::Some(4)"));
});

test("the shape of a value decides its children", () => {
  assert.equal(shapeOf("&str"), "string");
  assert.equal(shapeOf("*mut str"), "heap-string");
  assert.equal(shapeOf("*mut [int32]"), "heap-list");
  assert.equal(shapeOf("*mut [str: int32]"), "pointer");
  assert.equal(shapeOf("*mut Tree"), "pointer");
  assert.equal(shapeOf("[int32; 3]"), "array");
  assert.equal(shapeOf("[int32; variable length]"), "array");
  assert.equal(shapeOf("Point"), "plain");
});

test("expressions for children, in gdb's Rust syntax", () => {
  assert.equal(childPath("p", "x", "Point"), "p.x");
  assert.equal(childPath("t", "__1", "(int32, bool)"), "t.1");
  assert.equal(childPath("xs", "2", "[int32; 3]"), "xs[2]");
  // a field through a pointer to a cell
  assert.equal(childPath("bag.items", "len", "*mut [int32]"), "(*bag.items).len");
  // an enum's variant fields: gdb reads `s.0` on the active variant
  assert.equal(childPath("s", "__0", "Shape::Circle"), "s.0");
  assert.equal(childPath("a + b", "x", "Point"), "(a + b).x");
  assert.equal(childPath(undefined, "x", "Point"), undefined);
});

test("child names", () => {
  assert.equal(displayChildName("__0", "(int32, bool)"), "0");
  assert.equal(displayChildName("3", "[int32; 5]"), "[3]");
  assert.equal(displayChildName("x", "Point"), "x");
});

test("strings for the Variables view", () => {
  assert.equal(quoteMylaString('two "q"\n\\'), '"two \\"q\\"\\n\\\\"');
  assert.equal(quoteMylaString("héllo"), '"héllo"');
});

test("little-endian numbers from memory read as hex", () => {
  assert.equal(readLittleEndian("1000000000000000", 0, 8), 16);
  assert.equal(readLittleEndian("d051400000000000190000000e000000", 8, 4), 25);
  assert.equal(readLittleEndian("d051400000000000190000000e000000", 12, 4), 14);
  assert.equal(readLittleEndian("d051400000000000190000000e000000", 0, 8), 0x4051d0);
});
