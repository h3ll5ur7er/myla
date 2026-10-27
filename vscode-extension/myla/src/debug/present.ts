// Presenting what gdb reports in Myla's terms: function names, stop reasons,
// which values expand and how their children are reached. The DWARF of
// `myla build -g` says the program is Rust (D75), so gdb prints values and
// reads expressions in Rust syntax, which is close to Myla's.

/** A function's label as Myla names it: `myla_geometry$area` is `geometry.area`. */
export function functionName(label: string): string {
  if (!label) return "??";
  if (!label.startsWith("myla_")) return label;
  let name = label.slice("myla_".length).replace(/\$/g, ".");
  let m = /^__lambda_(\d+)$/.exec(name);
  if (m) return `<lambda ${m[1]}>`;
  m = /^(.*)__lam(\d+)$/.exec(name);
  if (m) name = `${m[1]}.<lambda ${m[2]}>`;
  return name;
}

/** The runtime's own code (`__panic`, `__alloc`, `_start`) has no Myla source. */
export function isRuntimeFrame(label: string): boolean {
  return label.startsWith("__") || label === "_start";
}

const SIGNAL_NUMBERS: Record<string, number> = {
  SIGHUP: 1, SIGINT: 2, SIGQUIT: 3, SIGILL: 4, SIGTRAP: 5, SIGABRT: 6, SIGBUS: 7, SIGFPE: 8,
  SIGKILL: 9, SIGSEGV: 11, SIGPIPE: 13, SIGALRM: 14, SIGTERM: 15,
};

/** gdb writes exit codes in octal (`exit-code="012"` is 10). */
export function parseExitCode(text: string): number {
  return text ? parseInt(text, 8) : 0;
}

export interface StopContext {
  /** The breakpoint on `__panic`, which every runtime error calls (D75). */
  panicBreakpoint?: number;
  /** The temporary breakpoint on `main` for `stopOnEntry`. */
  entryBreakpoint?: number;
  functionBreakpoints: Set<number>;
  pauseRequested: boolean;
}

export type Stop =
  | { reason: "breakpoint" | "function breakpoint"; breakpoint: number }
  | { reason: "step" | "pause" | "entry" | "goto" }
  | { reason: "exception"; description?: string }
  | { exited: number; description?: string };

/** The DAP stop reason for a `*stopped` record, or how the program ended. */
export function stopReason(results: Record<string, unknown>, ctx: StopContext): Stop {
  const str = (k: string) => (typeof results[k] === "string" ? (results[k] as string) : "");
  switch (str("reason")) {
    case "breakpoint-hit": {
      const n = Number(str("bkptno"));
      if (n === ctx.panicBreakpoint) return { reason: "exception" };
      if (n === ctx.entryBreakpoint) return { reason: "entry" };
      if (ctx.functionBreakpoints.has(n)) return { reason: "function breakpoint", breakpoint: n };
      return { reason: "breakpoint", breakpoint: n };
    }
    case "end-stepping-range":
    case "function-finished":
    case "location-reached":
      return { reason: "step" };
    case "signal-received": {
      const name = str("signal-name");
      if (name === "SIGINT" || name === "0" || ctx.pauseRequested) return { reason: "pause" };
      const meaning = str("signal-meaning");
      return { reason: "exception", description: meaning ? `${name}: ${meaning}` : name };
    }
    case "exited-normally":
      return { exited: 0 };
    case "exited":
      return { exited: parseExitCode(str("exit-code")) };
    case "exited-signalled": {
      const name = str("signal-name");
      return { exited: 128 + (SIGNAL_NUMBERS[name] ?? 0), description: name };
    }
    default:
      // e.g. `-exec-interrupt` reports no reason in some gdb versions
      return { reason: ctx.pauseRequested ? "pause" : "step" };
  }
}

const SCALARS = /^(u?int(8|16|32|64)|float(32|64)|bool|char)$/;

/** How a value of this gdb type is shown. */
export type Shape = "string" | "heap-string" | "heap-list" | "array" | "pointer" | "plain";

export function shapeOf(type: string): Shape {
  if (type === "&str") return "string";
  if (type === "*mut str") return "heap-string";
  // a list cell `*mut [T]`; a map cell is `*mut [K: V]`
  if (/^\*mut \[[^:]*\]$/.test(type)) return "heap-list";
  if (type.startsWith("*mut ") || type.startsWith("*const ")) return "pointer";
  if (/^\[.*; [^;]+\]$/.test(type)) return "array";
  return "plain";
}

/** Whether a value has children to show. */
export function isExpandable(type: string, value: string): boolean {
  if (SCALARS.test(type)) return false;
  const shape = shapeOf(type);
  if (shape === "string" || shape === "heap-string") return false;
  // an enum variant without fields, such as `Option<int32>::None`
  if (/^[\w<>, :]+::\w+$/.test(value)) return false;
  return true;
}

// a variable, a parenthesized dereference, then fields and indexes
const POSTFIX_SAFE = /^(\(\*[^()]*\)|\w+)(\.\w+|\[\d+\])*$/;

function postfix(path: string): string {
  return POSTFIX_SAFE.test(path) ? path : `(${path})`;
}

/**
 * The expression for child `exp` (as gdb's variable objects name it) of the
 * value at `parentPath` of type `parentType`: `p.x`, `t.1` for a tuple field
 * `__1` (also an enum variant's fields), `xs[2]`, `(*p).len` through a cell
 * pointer. Undefined when the parent's expression isn't known.
 */
export function childPath(parentPath: string | undefined, exp: string, parentType: string): string | undefined {
  if (parentPath === undefined) return undefined;
  const shape = shapeOf(parentType);
  const base = shape === "pointer" || shape === "heap-list" || shape === "heap-string" ? `(*${parentPath})` : postfix(parentPath);
  if (/^\d+$/.test(exp)) return `${base}[${exp}]`;
  const tupleField = /^__(\d+)$/.exec(exp);
  if (tupleField) return `${base}.${tupleField[1]}`;
  return `${base}.${exp}`;
}

/** The name the Variables view shows for child `exp`. */
export function displayChildName(exp: string, parentType: string): string {
  if (/^\d+$/.test(exp) && shapeOf(parentType) === "array") return `[${exp}]`;
  const tupleField = /^__(\d+)$/.exec(exp);
  return tupleField ? tupleField[1] : exp;
}

/** A string as a Myla literal. */
export function quoteMylaString(text: string): string {
  return (
    '"' +
    text
      .replace(/\\/g, "\\\\")
      .replace(/"/g, '\\"')
      .replace(/\n/g, "\\n")
      .replace(/\r/g, "\\r")
      .replace(/\t/g, "\\t")
      .replace(/\0/g, "\\0") +
    '"'
  );
}

/** A little-endian unsigned number of `size` bytes at byte `offset` of a hex dump. */
export function readLittleEndian(hex: string, offset: number, size: number): number {
  let n = 0;
  for (let i = size - 1; i >= 0; i--) {
    const byte = parseInt(hex.slice((offset + i) * 2, (offset + i) * 2 + 2), 16);
    n = n * 256 + (Number.isNaN(byte) ? 0 : byte);
  }
  return n;
}
