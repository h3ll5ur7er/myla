// Building a Myla program with debug information, and reading the compiler's
// diagnostics. Needs nothing from VS Code: the extension and the standalone
// debug adapter both use it.
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import * as path from "node:path";
import type { Toolchain } from "./toolchain.ts";

/** One diagnostic the compiler (or a runtime error) printed. */
export interface CompilerDiagnostic {
  file: string;
  line: number;
  column: number;
  /** One past the last underlined column, when the compiler showed a range. */
  endColumn?: number;
  severity: "error" | "warning";
  message: string;
}

const HEADLINE = /^(?:\w+ )?(error|warning): (.*)$/;
const LOCATION = /^\s*--> (.+):(\d+):(\d+)\s*$/;
const CARETS = /^\s*\|\s*(\^+)\s*$/;

/**
 * The diagnostics in the output of `myla build`, `run` or `check`: a headline
 * `<stage> error: <message>`, then `  --> file:line:col`, then optionally the
 * source line and carets under the range (D74). Relative files are taken
 * relative to `cwd`.
 */
export function parseDiagnostics(output: string, cwd?: string): CompilerDiagnostic[] {
  const lines = output.split(/\r?\n/);
  const out: CompilerDiagnostic[] = [];
  for (let i = 0; i + 1 < lines.length; i++) {
    const head = HEADLINE.exec(lines[i]);
    const at = head && LOCATION.exec(lines[i + 1]);
    if (!head || !at) continue;
    const file = cwd && !path.isAbsolute(at[1]) ? path.resolve(cwd, at[1]) : at[1];
    const d: CompilerDiagnostic = {
      file,
      line: Number(at[2]),
      column: Number(at[3]),
      severity: head[1] as "error" | "warning",
      message: lines[i],
    };
    // `  |`, `N | source`, `  | ^^^`
    const carets = lines[i + 4] !== undefined ? CARETS.exec(lines[i + 4]) : null;
    if (carets && /^\s*\d+ \|/.test(lines[i + 3] ?? "")) d.endColumn = d.column + carets[1].length;
    out.push(d);
    i++;
  }
  return out;
}

/** `myla build <file> -o <output> [-g]`. */
export function buildCommand(cli: Toolchain, file: string, output: string, debug: boolean): Toolchain {
  return { command: cli.command, args: [...cli.args, "build", file, "-o", output, ...(debug ? ["-g"] : [])] };
}

/** What a launch configuration's `program` names. */
export type DebugTarget =
  | { kind: "file"; file: string }
  | { kind: "binary"; path: string }
  | { kind: "project"; root: string }
  | { kind: "missing"; message: string };

/**
 * `program` is a `.my` file to build, a binary built with `-g`, or a project
 * (its directory or `myla.toml`, D73), which `projectBuild` builds with the
 * project's own `myla build` (MYLA-94).
 */
export function debugTarget(
  program: string,
  fs: { isFile(p: string): boolean; isDirectory(p: string): boolean },
): DebugTarget {
  const projectRoot = fs.isDirectory(program)
    ? program
    : path.basename(program) === "myla.toml" && fs.isFile(program)
      ? path.dirname(program)
      : undefined;
  if (projectRoot !== undefined) {
    const main = path.join(projectRoot, "src", "main.my");
    if (fs.isFile(path.join(projectRoot, "myla.toml")) && fs.isFile(main)) {
      return { kind: "project", root: projectRoot };
    }
    return { kind: "missing", message: `${program} is not a Myla project with a src/main.my.` };
  }
  if (!fs.isFile(program)) return { kind: "missing", message: `The program to debug doesn't exist: ${program}` };
  return program.endsWith(".my") ? { kind: "file", file: program } : { kind: "binary", path: program };
}

/** How to build a project for the debugger: the command, where to run it, and the binary it writes. */
export interface ProjectBuild {
  command: Toolchain;
  cwd: string;
  executable: string;
}

/**
 * A project is built by `myla build -g` in its directory, which resolves its
 * dependencies and writes `build/<name>` (MYLA-94). `manifest` is the text of
 * its `myla.toml`.
 */
export function projectBuild(cli: Toolchain, root: string, manifest: string): ProjectBuild | { missing: string } {
  const name = packageName(manifest);
  if (name === undefined) return { missing: `${path.join(root, "myla.toml")} has no package.name.` };
  return {
    command: { command: cli.command, args: [...cli.args, "build", "-g"] },
    cwd: root,
    executable: path.join(root, "build", name),
  };
}

/** The `name` of a manifest's `[package]` table (a basic or literal string), if it has one. */
export function packageName(manifest: string): string | undefined {
  let table = "";
  for (const raw of manifest.split(/\r?\n/)) {
    const line = raw.trim();
    const header = /^\[\s*([^\]]*?)\s*\]/.exec(line);
    if (header) {
      table = header[1];
      continue;
    }
    const entry = /^name\s*=\s*(?:"([^"]*)"|'([^']*)')/.exec(line);
    if (table === "package" && entry) return entry[1] ?? entry[2];
  }
  return undefined;
}

/** Where the debug build of `file` goes: `<dir>/<name>-<hash of its path>`. */
export function debugOutputPath(dir: string, file: string): string {
  const hash = createHash("sha256").update(path.resolve(file)).digest("hex").slice(0, 8);
  return path.join(dir, `${path.basename(file, ".my")}-${hash}`);
}

export interface BuildResult {
  ok: boolean;
  /** stdout and stderr of the compiler, as it printed them. */
  output: string;
  diagnostics: CompilerDiagnostic[];
}

/** Runs `command` in `cwd` and reports how the build went. */
export function runBuild(command: Toolchain, cwd: string): Promise<BuildResult> {
  return new Promise((resolve) => {
    let output = "";
    let settled = false;
    const finish = (ok: boolean) => {
      if (settled) return;
      settled = true;
      resolve({ ok, output, diagnostics: parseDiagnostics(output, cwd) });
    };
    const child = spawn(command.command, command.args, { cwd, stdio: ["ignore", "pipe", "pipe"] });
    child.stdout.setEncoding("utf8").on("data", (d: string) => (output += d));
    child.stderr.setEncoding("utf8").on("data", (d: string) => (output += d));
    // the command doesn't exist or can't run
    child.on("error", (err) => {
      output += `${command.command}: ${err.message}\n`;
      finish(false);
    });
    child.on("close", (code) => finish(code === 0));
  });
}
