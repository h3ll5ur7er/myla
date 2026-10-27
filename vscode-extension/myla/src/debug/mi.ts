// GDB/MI: parsing gdb's output records and quoting command arguments
// (https://sourceware.org/gdb/current/onlinedocs/gdb.html/GDB_002fMI-Output-Syntax.html).
// Nothing here knows about VS Code or Myla.

/** An MI value: a C string, a tuple `{a="1"}` or a list `[...]`. */
export type MiValue = string | MiTuple | MiValue[];
export interface MiTuple {
  [key: string]: MiValue;
}

export type MiRecord =
  | { kind: "result"; token?: number; resultClass: string; results: MiTuple }
  | { kind: "exec" | "status" | "notify"; token?: number; asyncClass: string; results: MiTuple }
  | { kind: "console" | "target" | "log"; text: string }
  | { kind: "prompt" }
  | { kind: "other"; text: string };

const ASYNC_KINDS = { "*": "exec", "+": "status", "=": "notify" } as const;
const STREAM_KINDS = { "~": "console", "@": "target", "&": "log" } as const;

class Cursor {
  pos = 0;
  readonly text: string;
  constructor(text: string) {
    this.text = text;
  }
  peek(): string {
    return this.text[this.pos] ?? "";
  }
  expect(ch: string): void {
    if (this.text[this.pos] !== ch) throw new SyntaxError(`expected ${ch} at ${this.pos}`);
    this.pos++;
  }
  atEnd(): boolean {
    return this.pos >= this.text.length;
  }
}

const SIMPLE_ESCAPES: Record<string, number> = {
  n: 10, t: 9, r: 13, '"': 34, "\\": 92, a: 7, b: 8, f: 12, v: 11, e: 27, "'": 39,
};

/** A C string; gdb writes bytes beyond ASCII as octal escapes of their UTF-8. */
function parseCString(c: Cursor): string {
  c.expect('"');
  const bytes: number[] = [];
  const text = c.text;
  for (;;) {
    if (c.atEnd()) throw new SyntaxError("unterminated string");
    const ch = text[c.pos++];
    if (ch === '"') break;
    if (ch !== "\\") {
      const code = ch.codePointAt(0)!;
      if (code < 0x80) bytes.push(code);
      else {
        // already a character (gdb doesn't do this, but don't mangle it)
        const cp = text.codePointAt(c.pos - 1)!;
        if (cp > 0xffff) c.pos++;
        bytes.push(...Buffer.from(String.fromCodePoint(cp), "utf8"));
      }
      continue;
    }
    const esc = text[c.pos++];
    if (esc === undefined) throw new SyntaxError("unterminated escape");
    if (esc in SIMPLE_ESCAPES) {
      bytes.push(SIMPLE_ESCAPES[esc]);
    } else if (esc >= "0" && esc <= "7") {
      let digits = esc;
      while (digits.length < 3 && text[c.pos] >= "0" && text[c.pos] <= "7") digits += text[c.pos++];
      bytes.push(parseInt(digits, 8) & 0xff);
    } else if (esc === "x") {
      let digits = "";
      while (/[0-9a-fA-F]/.test(text[c.pos] ?? "")) digits += text[c.pos++];
      bytes.push(parseInt(digits || "0", 16) & 0xff);
    } else {
      bytes.push(...Buffer.from(esc, "utf8"));
    }
  }
  return Buffer.from(bytes).toString("utf8");
}

function parseVariable(c: Cursor): string {
  const start = c.pos;
  while (!c.atEnd() && c.peek() !== "=") c.pos++;
  if (c.pos === start) throw new SyntaxError(`expected a name at ${start}`);
  return c.text.slice(start, c.pos);
}

function parseValue(c: Cursor): MiValue {
  const ch = c.peek();
  if (ch === '"') return parseCString(c);
  if (ch === "{") return parseTuple(c);
  if (ch === "[") return parseList(c);
  throw new SyntaxError(`unexpected ${JSON.stringify(ch)} at ${c.pos}`);
}

function parseTuple(c: Cursor): MiTuple {
  c.expect("{");
  const out: MiTuple = {};
  if (c.peek() === "}") {
    c.pos++;
    return out;
  }
  for (;;) {
    const name = parseVariable(c);
    c.expect("=");
    out[name] = parseValue(c);
    if (c.peek() === ",") {
      c.pos++;
      continue;
    }
    c.expect("}");
    return out;
  }
}

/** A list of values or of results; the names of results (always the same,
 * like `frame=` or `child=`) are dropped. */
function parseList(c: Cursor): MiValue[] {
  c.expect("[");
  const out: MiValue[] = [];
  if (c.peek() === "]") {
    c.pos++;
    return out;
  }
  for (;;) {
    const ch = c.peek();
    if (ch !== '"' && ch !== "{" && ch !== "[") {
      parseVariable(c);
      c.expect("=");
    }
    out.push(parseValue(c));
    if (c.peek() === ",") {
      c.pos++;
      continue;
    }
    c.expect("]");
    return out;
  }
}

function parseResults(c: Cursor): MiTuple {
  const out: MiTuple = {};
  while (c.peek() === ",") {
    c.pos++;
    const name = parseVariable(c);
    c.expect("=");
    out[name] = parseValue(c);
  }
  if (!c.atEnd()) throw new SyntaxError(`trailing text at ${c.pos}`);
  return out;
}

function parseClass(c: Cursor): string {
  const start = c.pos;
  while (!c.atEnd() && c.peek() !== ",") c.pos++;
  return c.text.slice(start, c.pos);
}

/** One line of gdb's output. Text that isn't an MI record is `other`. */
export function parseMiLine(raw: string): MiRecord {
  const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
  if (line.trimEnd() === "(gdb)") return { kind: "prompt" };
  try {
    const c = new Cursor(line);
    const first = c.peek();
    if (first in STREAM_KINDS) {
      c.pos++;
      const text = parseCString(c);
      if (!c.atEnd()) throw new SyntaxError("trailing text");
      return { kind: STREAM_KINDS[first as keyof typeof STREAM_KINDS], text };
    }
    let digits = "";
    while (c.peek() >= "0" && c.peek() <= "9") digits += line[c.pos++];
    const token = digits ? Number(digits) : undefined;
    const marker = c.peek();
    if (marker === "^") {
      c.pos++;
      const resultClass = parseClass(c);
      return { kind: "result", token, resultClass, results: parseResults(c) };
    }
    if (marker in ASYNC_KINDS) {
      c.pos++;
      const asyncClass = parseClass(c);
      // `+download,{...}` carries an unnamed tuple; keep the class, skip the rest
      if (marker === "+") return { kind: "status", token, asyncClass, results: {} };
      return { kind: ASYNC_KINDS[marker as keyof typeof ASYNC_KINDS], token, asyncClass, results: parseResults(c) };
    }
  } catch {
    // not an MI record after all
  }
  return { kind: "other", text: line };
}

/** `value` as a string ("" when it is missing or not a string). */
export function miString(value: MiValue | undefined): string {
  return typeof value === "string" ? value : "";
}

/** `value` as a tuple ({} when it is missing or not a tuple). */
export function miTuple(value: MiValue | undefined): MiTuple {
  return value !== undefined && typeof value === "object" && !Array.isArray(value) ? value : {};
}

/** `value` as a list ([] when it is missing or not a list). */
export function miList(value: MiValue | undefined): MiValue[] {
  return Array.isArray(value) ? value : [];
}

/** A C string for an MI command argument. */
export function miQuote(text: string): string {
  return '"' + text.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n").replace(/\r/g, "\\r") + '"';
}
