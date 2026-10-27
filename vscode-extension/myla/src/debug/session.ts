// The Myla debug adapter: the Debug Adapter Protocol on one side, gdb's MI
// interpreter on the other (D78). It needs nothing from VS Code: the extension
// runs it in-process (DebugAdapterInlineImplementation) and adapterMain.ts on
// stdio, which is how the integration test drives it.
import type { DebugProtocol } from "@vscode/debugprotocol";
import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { StringDecoder } from "node:string_decoder";
import { buildCommand, debugOutputPath, debugTarget, runBuild } from "../build.ts";
import { chooseCli } from "../toolchain.ts";
import { Gdb, MiError, type MiTransport } from "./gdb.ts";
import { miList, miQuote, miString, miTuple, type MiRecord, type MiTuple } from "./mi.ts";
import {
  childPath,
  displayChildName,
  functionName,
  isExpandable,
  isRuntimeFrame,
  quoteMylaString,
  readLittleEndian,
  shapeOf,
  stopReason,
  type StopContext,
} from "./present.ts";

/** The `launch` configuration (package.json's `configurationAttributes`). */
export interface LaunchArguments extends DebugProtocol.LaunchRequestArguments {
  /** A .my file (built with -g first), a binary built with -g, or a project. */
  program: string;
  /** The binary to debug when it is already built (the extension builds
   * `program` before launching and passes it here). */
  executable?: string;
  args?: string[];
  cwd?: string;
  env?: Record<string, string>;
  stdin?: string;
  stopOnEntry?: boolean;
  gdbPath?: string;
  /** The myla CLI that builds `program` when `executable` is missing. */
  cliPath?: string;
  /** Show the MI conversation in the debug console. */
  trace?: boolean;
}

/** A variable or evaluate result whose children can be listed. */
type Handle =
  | { kind: "scope"; scope: "locals" | "arguments"; thread: number; level: number }
  | { kind: "expression"; expression: string; type: string; thread?: number; level?: number }
  | { kind: "varobj"; varobj: string; path?: string; type: string; thread?: number; level?: number };

/** A child of a handle, by the name the Variables view shows, for setVariable. */
interface Assignable {
  varobj?: string;
  expression?: string;
  thread?: number;
  level?: number;
}

interface VarobjChild {
  name: string;
  exp: string;
  numchild: number;
  value: string;
  type: string;
}

interface Frame {
  thread: number;
  level: number;
}

const RUNTIME_ERROR_FILTER = "runtime-error";
/** Strings longer than this are cut when read from memory. */
const MAX_STRING_BYTES = 4096;

/** A word for a POSIX shell: gdb starts the program through /bin/sh. */
export function shellQuote(word: string): string {
  return /^[\w@%+=:,./-]+$/.test(word) ? word : `'${word.replace(/'/g, `'\\''`)}'`;
}

export interface SessionOptions {
  /** Starts gdb; tests pass a fake. */
  startGdb?: (gdbPath: string, cwd: string, env: NodeJS.ProcessEnv) => Promise<MiTransport>;
  /** How often program output is collected while it runs, in ms. */
  pollInterval?: number;
}

export class MylaDebugSession {
  private readonly sendMessage: (message: DebugProtocol.ProtocolMessage) => void;
  private readonly startGdb: (gdbPath: string, cwd: string, env: NodeJS.ProcessEnv) => Promise<MiTransport>;
  private readonly pollInterval: number;
  private seq = 1;
  private chain: Promise<void> = Promise.resolve();

  private gdb: MiTransport | undefined;
  private launchArgs: LaunchArguments | undefined;
  private tempDir: string | undefined;
  private cwd = process.cwd();
  private outputs: { file: string; offset: number; decoder: StringDecoder; category: string }[] = [];
  private poller: NodeJS.Timeout | undefined;
  private running = false;
  private started = false;
  private ended = false;
  private terminating = false;
  private threadId = 1;
  /** Stops the program of a `noDebug` launch. */
  private disposeChild: (() => void) | undefined;

  private readonly stopContext: StopContext = { functionBreakpoints: new Set(), pauseRequested: false };
  private readonly sourceBreakpoints = new Map<string, number[]>();
  private functionBreakpointNumbers: number[] = [];
  private exception: DebugProtocol.ExceptionInfoResponse["body"] | undefined;

  // valid while the program is stopped
  private handles = new Map<number, Handle>();
  private frames = new Map<number, Frame>();
  private assignables = new Map<number, Map<string, Assignable>>();
  private nextHandle = 1;
  private rootVarobjs: string[] = [];

  constructor(sendMessage: (message: DebugProtocol.ProtocolMessage) => void, options: SessionOptions = {}) {
    this.sendMessage = sendMessage;
    this.startGdb = options.startGdb ?? Gdb.start;
    this.pollInterval = options.pollInterval ?? 100;
  }

  /** One message from the client. Requests are handled in order, except
   * those that must not wait (pause, disconnect, terminate). */
  handleMessage(message: DebugProtocol.ProtocolMessage): void {
    if (message.type !== "request") return;
    const request = message as DebugProtocol.Request;
    if (["pause", "disconnect", "terminate"].includes(request.command)) {
      void this.dispatch(request);
    } else {
      this.chain = this.chain.then(() => this.dispatch(request));
    }
  }

  /** Stops gdb and removes temporary files. */
  dispose(): void {
    this.stopPolling();
    this.gdb?.kill();
    this.removeTempDir();
  }

  // --- protocol -------------------------------------------------------------

  private async dispatch(request: DebugProtocol.Request): Promise<void> {
    try {
      const body = await this.handle(request);
      this.sendMessage({
        seq: this.seq++,
        type: "response",
        request_seq: request.seq,
        command: request.command,
        success: true,
        body,
      } as DebugProtocol.Response);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this.sendMessage({
        seq: this.seq++,
        type: "response",
        request_seq: request.seq,
        command: request.command,
        success: false,
        message,
        body: { error: { id: 1, format: message.replace(/[{}]/g, ""), showUser: request.command === "launch" } },
      } as DebugProtocol.ErrorResponse);
    }
  }

  private sendEvent(event: string, body?: unknown): void {
    this.sendMessage({ seq: this.seq++, type: "event", event, body } as DebugProtocol.Event);
  }

  private output(text: string, category = "console"): void {
    if (text) this.sendEvent("output", { category, output: text });
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private async handle(request: DebugProtocol.Request): Promise<any> {
    const args = request.arguments ?? {};
    switch (request.command) {
      case "initialize":
        return this.initialize();
      case "launch":
        return this.launch(args as LaunchArguments);
      case "setBreakpoints":
        return this.setBreakpoints(args as DebugProtocol.SetBreakpointsArguments);
      case "setFunctionBreakpoints":
        return this.setFunctionBreakpoints(args as DebugProtocol.SetFunctionBreakpointsArguments);
      case "setExceptionBreakpoints":
        return this.setExceptionBreakpoints(args as DebugProtocol.SetExceptionBreakpointsArguments);
      case "configurationDone":
        return this.configurationDone();
      case "threads":
        return { threads: [{ id: this.threadId, name: "main" }] };
      case "stackTrace":
        return this.stackTrace(args as DebugProtocol.StackTraceArguments);
      case "scopes":
        return this.scopes(args as DebugProtocol.ScopesArguments);
      case "variables":
        return this.variables(args as DebugProtocol.VariablesArguments);
      case "setVariable":
        return this.setVariable(args as DebugProtocol.SetVariableArguments);
      case "evaluate":
        return this.evaluate(args as DebugProtocol.EvaluateArguments);
      case "exceptionInfo":
        if (!this.exception) throw new Error("The program didn't stop on a runtime error.");
        return this.exception;
      case "continue":
        await this.resume("-exec-continue");
        return { allThreadsContinued: true };
      case "next":
        return this.resume("-exec-next");
      case "stepIn":
        return this.resume("-exec-step");
      case "stepOut":
        return this.resume("-exec-finish");
      case "pause":
        return this.pause();
      case "terminate":
        return this.terminate();
      case "disconnect":
        return this.disconnect();
      default:
        throw new Error(`The Myla debugger doesn't support '${request.command}'.`);
    }
  }

  private initialize(): DebugProtocol.Capabilities {
    return {
      supportsConfigurationDoneRequest: true,
      supportsFunctionBreakpoints: true,
      supportsConditionalBreakpoints: true,
      supportsHitConditionalBreakpoints: true,
      supportsEvaluateForHovers: true,
      supportsSetVariable: true,
      supportsExceptionInfoRequest: true,
      supportsTerminateRequest: true,
      supportsDelayedStackTraceLoading: true,
      exceptionBreakpointFilters: [
        {
          filter: RUNTIME_ERROR_FILTER,
          label: "Runtime errors",
          description: "Stop where a runtime error happens: division by zero, an index out of range, panic, assert, …",
          default: true,
        },
      ],
    };
  }

  // --- launch ---------------------------------------------------------------

  private async launch(args: LaunchArguments): Promise<void> {
    this.launchArgs = args;
    this.tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "myla-debug-"));
    const program = path.resolve(args.cwd || process.cwd(), args.program ?? "");
    this.cwd = args.cwd || path.dirname(program);
    const executable = args.executable ?? (await this.buildProgram(program, args.cliPath));

    if (args.noDebug) {
      this.runWithoutDebugging(executable, args);
      return;
    }

    const env: NodeJS.ProcessEnv = { ...process.env, SHELL: "/bin/sh" };
    try {
      this.gdb = await this.startGdb(args.gdbPath || "gdb", this.cwd, env);
    } catch (err) {
      throw new Error(
        `Could not start gdb (${args.gdbPath || "gdb"}): ${err instanceof Error ? err.message : err}. Install gdb or set 'myla.debug.gdbPath'.`,
        { cause: err },
      );
    }
    const gdb = this.gdb;
    if (args.trace) gdb.onTrace((line, dir) => this.output(`${dir === "out" ? "->" : "<-"} ${line}\n`));
    gdb.onRecord((r) => this.onRecord(r));
    gdb.onExit((code) => {
      if (!this.ended) {
        this.output(`gdb exited unexpectedly (${code}).\n`, "stderr");
        this.end();
      }
    });

    await gdb.send("-gdb-set mi-async on");
    await gdb.send("-gdb-set confirm off");
    // strings are UTF-8; gdb's default charset in a C locale mangles them
    await gdb.send("-gdb-set charset UTF-8");
    try {
      await gdb.send(`-file-exec-and-symbols ${miQuote(executable)}`);
    } catch (err) {
      throw new Error(`gdb can't load ${executable}: ${err instanceof Error ? err.message : err}`, { cause: err });
    }
    // gdb starts the program through the shell, to redirect its output into
    // files the adapter forwards (a pipe of its own isn't possible without a pty)
    if (process.env.SHELL) await this.console(`set environment SHELL=${process.env.SHELL}`);
    for (const [key, value] of Object.entries(args.env ?? {})) await this.console(`set environment ${key}=${value}`);
    const out = path.join(this.tempDir, "stdout");
    const err = path.join(this.tempDir, "stderr");
    fs.writeFileSync(out, "");
    fs.writeFileSync(err, "");
    this.outputs = [
      { file: out, offset: 0, decoder: new StringDecoder("utf8"), category: "stdout" },
      { file: err, offset: 0, decoder: new StringDecoder("utf8"), category: "stderr" },
    ];
    const stdin = args.stdin ? path.resolve(this.cwd, args.stdin) : "/dev/null";
    const words = (args.args ?? []).map(shellQuote);
    await this.console(`set args ${[...words, "<", shellQuote(stdin), ">", shellQuote(out), "2>", shellQuote(err)].join(" ")}`);
    // the client sends breakpoints now, then configurationDone
    setImmediate(() => this.sendEvent("initialized"));
  }

  /** Builds `program` with -g into the temporary directory. */
  private async buildProgram(program: string, cliPath: string | undefined): Promise<string> {
    const target = debugTarget(program, {
      isFile: (p) => fs.statSync(p, { throwIfNoEntry: false })?.isFile() ?? false,
      isDirectory: (p) => fs.statSync(p, { throwIfNoEntry: false })?.isDirectory() ?? false,
    });
    if (target.kind === "missing") throw new Error(target.message);
    if (target.kind === "binary") return target.path;
    const file = target.kind === "file" ? target.file : target.main;
    const cli = chooseCli({ cliPath: cliPath || "myla", compilerEntry: undefined }, fs.existsSync);
    if ("missing" in cli) throw new Error(cli.missing);
    const output = debugOutputPath(this.tempDir!, file);
    const command = buildCommand(cli, file, output, true);
    this.output(`${[command.command, ...command.args].join(" ")}\n`);
    const result = await runBuild(command, path.dirname(file));
    if (!result.ok) {
      this.output(result.output, "stderr");
      const first = result.diagnostics[0];
      throw new Error(first ? `Build failed: ${first.message} (${path.basename(first.file)}:${first.line})` : `Build failed: ${result.output.trim()}`);
    }
    return output;
  }

  /** `noDebug` (Run Without Debugging): the program runs on its own. */
  private runWithoutDebugging(executable: string, args: LaunchArguments): void {
    const stdin = args.stdin ? fs.openSync(path.resolve(this.cwd, args.stdin), "r") : "ignore";
    const child = spawn(executable, args.args ?? [], {
      cwd: this.cwd,
      env: { ...process.env, ...args.env },
      stdio: [stdin, "pipe", "pipe"],
    });
    child.stdout!.setEncoding("utf8").on("data", (d: string) => this.output(d, "stdout"));
    child.stderr!.setEncoding("utf8").on("data", (d: string) => this.output(d, "stderr"));
    child.on("error", (e) => this.output(`${e.message}\n`, "stderr"));
    child.on("close", (code, signal) => {
      if (typeof stdin === "number") fs.closeSync(stdin);
      const exitCode = code ?? 128 + (signal ? (os.constants.signals[signal] ?? 0) : 0);
      this.output(`Program exited with code ${exitCode}${signal ? ` (${signal})` : ""}.\n`);
      this.sendEvent("exited", { exitCode });
      this.end();
    });
    this.disposeChild = () => child.kill("SIGKILL");
    setImmediate(() => this.sendEvent("initialized"));
  }

  private async configurationDone(): Promise<void> {
    if (!this.gdb || this.started) return;
    if (this.launchArgs?.stopOnEntry) {
      try {
        this.stopContext.entryBreakpoint = Number(miString((await this.insertBreakpoint("-t myla_main")).number));
      } catch {
        this.output("No Myla main function to stop at: the program runs.\n");
      }
    }
    this.started = true;
    this.running = true;
    await this.gdb.send("-exec-run");
    this.poller = setInterval(() => this.drainOutput(), this.pollInterval);
  }

  // --- breakpoints ----------------------------------------------------------

  private async insertBreakpoint(location: string, condition?: string, hitCondition?: string): Promise<MiTuple> {
    let options = "";
    if (condition) options += `-c ${miQuote(condition)} `;
    const hits = hitCondition ? parseInt(hitCondition.replace(/^\s*(>=|==)?\s*/, ""), 10) : NaN;
    if (hits > 1) options += `-i ${hits - 1} `;
    const r = await this.requireGdb().send(`-break-insert ${options}${location}`);
    const bkpt = miTuple(r.results.bkpt);
    if (!miString(bkpt.number)) throw new MiError("gdb set no breakpoint");
    return bkpt;
  }

  private async setBreakpoints(args: DebugProtocol.SetBreakpointsArguments): Promise<{ breakpoints: DebugProtocol.Breakpoint[] }> {
    const gdb = this.requireGdb();
    const file = args.source.path ?? args.source.name ?? "";
    const old = this.sourceBreakpoints.get(file) ?? [];
    if (old.length) await gdb.send(`-break-delete ${old.join(" ")}`).catch(() => undefined);
    const numbers: number[] = [];
    const breakpoints: DebugProtocol.Breakpoint[] = [];
    for (const bp of args.breakpoints ?? []) {
      // the full path matches the file name a debug build records; a binary
      // built from a relative path knows the file by a shorter name
      let result: MiTuple | undefined;
      let error = "";
      for (const name of [file, path.basename(file)]) {
        try {
          result = await this.insertBreakpoint(`--source ${miQuote(name)} --line ${bp.line}`, bp.condition, bp.hitCondition);
          break;
        } catch (err) {
          error = err instanceof Error ? err.message : String(err);
        }
      }
      if (!result) {
        breakpoints.push({ verified: false, line: bp.line, message: error });
        continue;
      }
      const number = Number(miString(result.number));
      numbers.push(number);
      const line = Number(miString(result.line)) || bp.line;
      breakpoints.push({ id: number, verified: true, line, source: args.source });
    }
    this.sourceBreakpoints.set(file, numbers);
    return { breakpoints };
  }

  private async setFunctionBreakpoints(
    args: DebugProtocol.SetFunctionBreakpointsArguments,
  ): Promise<{ breakpoints: DebugProtocol.Breakpoint[] }> {
    const gdb = this.requireGdb();
    if (this.functionBreakpointNumbers.length) {
      await gdb.send(`-break-delete ${this.functionBreakpointNumbers.join(" ")}`).catch(() => undefined);
    }
    this.functionBreakpointNumbers = [];
    this.stopContext.functionBreakpoints.clear();
    const breakpoints: DebugProtocol.Breakpoint[] = [];
    for (const bp of args.breakpoints) {
      // `area`, `Point.len`, `geometry.area` (labelled `myla_geometry$area`)
      const candidates = [`myla_${bp.name}`, `myla_${bp.name.replace(".", "$")}`, bp.name];
      let result: MiTuple | undefined;
      let error = "";
      for (const label of candidates) {
        try {
          result = await this.insertBreakpoint(miQuote(label), bp.condition, bp.hitCondition);
          break;
        } catch (err) {
          error = err instanceof Error ? err.message : String(err);
        }
      }
      if (!result) {
        breakpoints.push({ verified: false, message: error });
        continue;
      }
      const number = Number(miString(result.number));
      this.functionBreakpointNumbers.push(number);
      this.stopContext.functionBreakpoints.add(number);
      breakpoints.push({ id: number, verified: true, line: Number(miString(result.line)) || undefined, ...this.sourceOf(result) });
    }
    return { breakpoints };
  }

  private async setExceptionBreakpoints(args: DebugProtocol.SetExceptionBreakpointsArguments): Promise<object> {
    const gdb = this.requireGdb();
    const want = args.filters.includes(RUNTIME_ERROR_FILTER);
    const have = this.stopContext.panicBreakpoint;
    if (want && have === undefined) {
      // every runtime error calls __panic with the message and its position (D75)
      try {
        const r = await gdb.send("-break-insert *__panic");
        this.stopContext.panicBreakpoint = Number(miString(miTuple(r.results.bkpt).number));
      } catch {
        // not a Myla binary: nothing to stop on
      }
    } else if (!want && have !== undefined) {
      await gdb.send(`-break-delete ${have}`).catch(() => undefined);
      this.stopContext.panicBreakpoint = undefined;
    }
    return {};
  }

  // --- running ----------------------------------------------------------------

  private async resume(command: string): Promise<void> {
    const gdb = this.requireGdb();
    if (this.running) throw new Error("The program is running.");
    if (this.ended) throw new Error("The program has ended.");
    await this.forgetStop();
    this.running = true;
    try {
      await gdb.send(command);
    } catch (err) {
      this.running = false;
      throw err;
    }
  }

  private async pause(): Promise<void> {
    if (!this.gdb || !this.running) return;
    this.stopContext.pauseRequested = true;
    await this.gdb.send("-exec-interrupt");
  }

  private async terminate(): Promise<void> {
    if (this.disposeChild) {
      this.disposeChild();
      return;
    }
    if (!this.gdb || this.ended) return;
    this.terminating = true;
    if (this.started) {
      if (this.running) await this.gdb.send("-exec-interrupt").catch(() => undefined);
      await this.console("kill").catch(() => undefined);
    }
    this.drainOutput();
    this.end();
  }

  private async disconnect(): Promise<void> {
    this.stopPolling();
    this.disposeChild?.();
    const gdb = this.gdb;
    if (gdb && !gdb.exited) {
      this.ended = true;
      const exited = new Promise<void>((resolve) => gdb.onExit(() => resolve()));
      gdb.send("-gdb-exit").catch(() => undefined);
      const timeout = new Promise<void>((resolve) => setTimeout(resolve, 2000));
      await Promise.race([exited, timeout]);
      gdb.kill();
    }
    this.removeTempDir();
  }

  private end(): void {
    if (this.ended) return;
    this.ended = true;
    this.running = false;
    this.stopPolling();
    this.sendEvent("terminated");
  }

  // --- records from gdb -------------------------------------------------------

  private onRecord(record: MiRecord): void {
    if (record.kind === "exec" && record.asyncClass === "stopped") {
      this.chain = this.chain.then(() => this.onStopped(record.results)).catch((err) => this.output(`${err}\n`, "stderr"));
    } else if (record.kind === "exec" && record.asyncClass === "running") {
      this.running = true;
    } else if (record.kind === "target" || record.kind === "other") {
      // not MI: output that reached gdb's own stdout
      this.output(record.kind === "other" ? record.text + "\n" : record.text, "stdout");
    } else if (record.kind === "log" && this.launchArgs?.trace) {
      this.output(record.text, "console");
    }
  }

  private async onStopped(results: MiTuple): Promise<void> {
    this.running = false;
    // the interrupt before `kill` stops the program on its way out
    if (this.terminating || this.ended) return;
    const stop = stopReason(results as Record<string, unknown>, this.stopContext);
    this.stopContext.pauseRequested = false;
    this.drainOutput();
    if ("exited" in stop) {
      this.output(`Program exited with code ${stop.exited}${stop.description ? ` (${stop.description})` : ""}.\n`);
      this.sendEvent("exited", { exitCode: stop.exited });
      this.end();
      return;
    }
    this.threadId = Number(miString(results["thread-id"])) || this.threadId;
    const frame = miTuple(results.frame);
    // stepping off the end of main lands in _start, which has no source: go on
    if (stop.reason === "step" && miString(frame.func) === "_start") {
      this.running = true;
      await this.requireGdb().send("-exec-continue");
      return;
    }
    this.exception = undefined;
    const body: DebugProtocol.StoppedEvent["body"] = {
      reason: stop.reason,
      threadId: this.threadId,
      allThreadsStopped: true,
    };
    if ("breakpoint" in stop) body.hitBreakpointIds = [stop.breakpoint];
    if (stop.reason === "exception") {
      if (stop.description === undefined) {
        const panic = await this.readPanic();
        body.description = `Runtime error: ${panic.message}`;
        body.text = panic.message;
        this.exception = {
          exceptionId: "runtime error",
          description: panic.message,
          breakMode: "always",
          details: { message: panic.message, stackTrace: panic.position ? `  --> ${panic.position}` : undefined },
        };
      } else {
        body.description = stop.description;
        body.text = stop.description;
        this.exception = { exceptionId: "signal", description: stop.description, breakMode: "always" };
      }
    }
    this.sendEvent("stopped", body);
  }

  /** The message and position `__panic` was called with (`%rdi`, `%rsi`). */
  private async readPanic(): Promise<{ message: string; position?: string }> {
    const message = (await this.readMylaString("$rdi", 0)) ?? "unknown error";
    let position: string | undefined;
    try {
      const record = await this.readMemory("$rsi", 16, 0);
      const file = await this.readMylaString(`0x${readLittleEndian(record, 0, 8).toString(16)}`, 0);
      if (file !== undefined) position = `${file}:${readLittleEndian(record, 8, 4)}:${readLittleEndian(record, 12, 4)}`;
    } catch {
      // `panic` passes no position when there is none
    }
    return { message, position };
  }

  private async readMemory(address: string, length: number, level?: number): Promise<string> {
    const frame = level === undefined ? "" : `--thread ${this.threadId} --frame ${level} `;
    const r = await this.requireGdb().send(`-data-read-memory-bytes ${frame}${miQuote(address)} ${length}`);
    return miString(miTuple(miList(r.results.memory)[0]).contents);
  }

  /** A Myla string cell `[len:8][bytes]` at `address`. */
  private async readMylaString(address: string, level?: number): Promise<string | undefined> {
    try {
      const length = readLittleEndian(await this.readMemory(address, 8, level), 0, 8);
      if (length === 0) return "";
      const n = Math.min(length, MAX_STRING_BYTES);
      const hex = await this.readMemory(`${address}+8`, n, level);
      const text = Buffer.from(hex, "hex").toString("utf8");
      return length > n ? text + "…" : text;
    } catch {
      return undefined;
    }
  }

  // --- program output ---------------------------------------------------------

  private drainOutput(): void {
    for (const o of this.outputs) {
      let fd: number;
      try {
        fd = fs.openSync(o.file, "r");
      } catch {
        continue;
      }
      try {
        const chunk = Buffer.alloc(64 * 1024);
        for (;;) {
          const n = fs.readSync(fd, chunk, 0, chunk.length, o.offset);
          if (n <= 0) break;
          o.offset += n;
          this.output(o.decoder.write(chunk.subarray(0, n)), o.category);
        }
      } finally {
        fs.closeSync(fd);
      }
    }
  }

  private stopPolling(): void {
    if (this.poller) clearInterval(this.poller);
    this.poller = undefined;
  }

  private removeTempDir(): void {
    if (this.tempDir) fs.rmSync(this.tempDir, { recursive: true, force: true });
    this.tempDir = undefined;
  }

  // --- stopped state ------------------------------------------------------------

  private addHandle(handle: Handle): number {
    const id = this.nextHandle++;
    this.handles.set(id, handle);
    return id;
  }

  /** Forgets frames, handles and variable objects before the program resumes. */
  private async forgetStop(): Promise<void> {
    const gdb = this.requireGdb();
    const roots = this.rootVarobjs.splice(0);
    for (const v of roots) await gdb.send(`-var-delete ${miQuote(v)}`).catch(() => undefined);
    this.handles.clear();
    this.frames.clear();
    this.assignables.clear();
    this.exception = undefined;
  }

  private sourceOf(frame: MiTuple): { source?: DebugProtocol.Source } {
    const fullname = miString(frame.fullname);
    const file = miString(frame.file);
    if (!fullname && !file) return {};
    const resolved = path.resolve(this.cwd, fullname || file);
    return { source: { name: path.basename(resolved), path: resolved } };
  }

  private async stackTrace(args: DebugProtocol.StackTraceArguments): Promise<DebugProtocol.StackTraceResponse["body"]> {
    const gdb = this.requireGdb();
    const thread = args.threadId;
    const depth = Number(miString((await gdb.send(`-stack-info-depth --thread ${thread} 10000`)).results.depth));
    const low = args.startFrame ?? 0;
    const high = args.levels ? Math.min(depth, low + args.levels) - 1 : depth - 1;
    if (high < low) return { stackFrames: [], totalFrames: depth };
    const r = await gdb.send(`-stack-list-frames --thread ${thread} ${low} ${high}`);
    const stackFrames = miList(r.results.stack).map((value): DebugProtocol.StackFrame => {
      const f = miTuple(value);
      const level = Number(miString(f.level));
      const id = this.nextHandle++;
      this.frames.set(id, { thread, level });
      const label = miString(f.func);
      const { source } = this.sourceOf(f);
      return {
        id,
        name: functionName(label),
        source,
        line: Number(miString(f.line)) || 0,
        column: source ? 1 : 0,
        instructionPointerReference: miString(f.addr) || undefined,
        presentationHint: source && !isRuntimeFrame(label) ? "normal" : "subtle",
      };
    });
    return { stackFrames, totalFrames: depth };
  }

  private scopes(args: DebugProtocol.ScopesArguments): DebugProtocol.ScopesResponse["body"] {
    const frame = this.frames.get(args.frameId);
    if (!frame) throw new Error("Unknown frame.");
    return {
      scopes: [
        { name: "Locals", presentationHint: "locals", variablesReference: this.addHandle({ kind: "scope", scope: "locals", ...frame }), expensive: false },
        {
          name: "Arguments",
          presentationHint: "arguments",
          variablesReference: this.addHandle({ kind: "scope", scope: "arguments", ...frame }),
          expensive: false,
        },
      ],
    };
  }

  private async variables(args: DebugProtocol.VariablesArguments): Promise<{ variables: DebugProtocol.Variable[] }> {
    const handle = this.handles.get(args.variablesReference);
    if (!handle) return { variables: [] };
    const assignable = new Map<string, Assignable>();
    this.assignables.set(args.variablesReference, assignable);
    if (handle.kind === "scope") return { variables: await this.scopeVariables(handle, assignable) };
    const varobj = await this.varobjOf(handle, args.variablesReference);
    return { variables: await this.childrenOf(varobj, assignable, args.start, args.count) };
  }

  private async scopeVariables(
    scope: Extract<Handle, { kind: "scope" }>,
    assignable: Map<string, Assignable>,
  ): Promise<DebugProtocol.Variable[]> {
    const gdb = this.requireGdb();
    const where = `--thread ${scope.thread} --frame ${scope.level}`;
    // types from --simple-values, the values gdb prints from --all-values
    const typed = miList((await gdb.send(`-stack-list-variables ${where} --simple-values`)).results.variables).map(miTuple);
    const valued = miList((await gdb.send(`-stack-list-variables ${where} --all-values`)).results.variables).map(miTuple);
    const out: DebugProtocol.Variable[] = [];
    const seen = new Set<string>();
    typed.forEach((v, i) => {
      const isArg = miString(v.arg) === "1";
      if (isArg !== (scope.scope === "arguments")) return;
      const name = miString(v.name);
      const type = miString(v.type);
      const value = miString(valued[i]?.value);
      // gdb lists inner blocks first: a later variable of the same name is shadowed
      const shadowed = seen.has(name);
      seen.add(name);
      const expandable = !shadowed && isExpandable(type, value);
      out.push({
        name: shadowed ? `${name} (shadowed)` : name,
        value,
        type,
        evaluateName: shadowed ? undefined : name,
        variablesReference: expandable
          ? this.addHandle({ kind: "expression", expression: name, type, thread: scope.thread, level: scope.level })
          : 0,
        presentationHint: shadowed ? { visibility: "internal" } : undefined,
      });
      if (!shadowed) assignable.set(name, { expression: name, thread: scope.thread, level: scope.level });
    });
    return out;
  }

  /** Creates the variable object of an expression handle when first needed. */
  private async varobjOf(handle: Handle, ref: number): Promise<Extract<Handle, { kind: "varobj" }>> {
    if (handle.kind === "varobj") return handle;
    if (handle.kind !== "expression") throw new Error("not a value");
    const created = await this.createVarobj(handle.expression, handle.thread, handle.level);
    const varobj: Extract<Handle, { kind: "varobj" }> = {
      kind: "varobj",
      varobj: created.name,
      path: handle.expression,
      type: created.type || handle.type,
      thread: handle.thread,
      level: handle.level,
    };
    this.handles.set(ref, varobj);
    return varobj;
  }

  private async createVarobj(expression: string, thread?: number, level?: number): Promise<VarobjChild> {
    const where = level === undefined ? "" : `--thread ${thread} --frame ${level} `;
    const r = await this.requireGdb().send(`-var-create ${where}- * ${miQuote(expression)}`);
    const name = miString(r.results.name);
    this.rootVarobjs.push(name);
    return {
      name,
      exp: expression,
      numchild: Number(miString(r.results.numchild)),
      value: miString(r.results.value),
      type: miString(r.results.type),
    };
  }

  private async listChildren(varobj: string, start?: number, count?: number): Promise<VarobjChild[]> {
    const range = start !== undefined && count ? ` ${start} ${start + count}` : "";
    const r = await this.requireGdb().send(`-var-list-children --all-values ${miQuote(varobj)}${range}`);
    return miList(r.results.children).map((c) => {
      const t = miTuple(c);
      return {
        name: miString(t.name),
        exp: miString(t.exp),
        numchild: Number(miString(t.numchild)),
        value: miString(t.value),
        type: miString(t.type),
      };
    });
  }

  /** The children the Variables view shows: a list cell's elements, an
   * enum's active variant's fields, a struct's or tuple's fields. */
  private async childrenOf(
    handle: Extract<Handle, { kind: "varobj" }>,
    assignable: Map<string, Assignable>,
    start?: number,
    count?: number,
  ): Promise<DebugProtocol.Variable[]> {
    let varobj = handle.varobj;
    let type = handle.type;
    let parentPath = handle.path;
    if (shapeOf(type) === "heap-list") {
      // a list cell [len][cap][items]: show the items
      const items = (await this.listChildren(varobj)).find((c) => c.exp === "items");
      if (items) {
        parentPath = childPath(parentPath, "items", type);
        varobj = items.name;
        type = items.type;
      }
    }
    let kids = await this.listChildren(varobj, start, count);
    const tag = kids.find((c) => c.exp === "<tag>");
    if (tag) {
      // an enum: gdb shows the tag and the active variant; show its fields
      const variants = kids.filter((c) => c !== tag);
      if (variants.length === 1) {
        kids = variants[0].numchild > 0 ? await this.listChildren(variants[0].name) : [];
        type = variants[0].type;
      } else {
        kids = variants;
      }
    }
    const out: DebugProtocol.Variable[] = [];
    for (const kid of kids) {
      const kidPath = childPath(parentPath, kid.exp, type);
      const name = displayChildName(kid.exp, type);
      const value = await this.childValue(kid, kidPath, handle);
      const expandable = kid.numchild > 0 && isExpandable(kid.type, value);
      const shape = shapeOf(kid.type);
      out.push({
        name,
        value,
        type: kid.type,
        evaluateName: kidPath,
        variablesReference: expandable
          ? this.addHandle({ kind: "varobj", varobj: kid.name, path: kidPath, type: kid.type, thread: handle.thread, level: handle.level })
          : 0,
        indexedVariables: shape === "array" && kid.numchild > 100 ? kid.numchild : undefined,
      });
      assignable.set(name, { varobj: kid.name });
    }
    return out;
  }

  /** A child's value as gdb prints it, where its variable object only says
   * `{...}`, `[3]` or a cell's address. */
  private async childValue(kid: VarobjChild, kidPath: string | undefined, handle: Extract<Handle, { kind: "varobj" }>): Promise<string> {
    const shape = shapeOf(kid.type);
    if (shape === "heap-string") {
      const text = await this.readMylaString(kid.value);
      return text === undefined ? kid.value : quoteMylaString(text);
    }
    const summary = kid.value === "{...}" || /^\[\d+\]$/.test(kid.value) || shape === "pointer" || shape === "heap-list";
    if (!summary || kidPath === undefined) return kid.value;
    const expression = shape === "heap-list" ? `(*${kidPath}).items` : shape === "pointer" ? `*${kidPath}` : kidPath;
    const pretty = await this.evaluateQuietly(expression, handle.thread, handle.level);
    return pretty ?? (kid.value === "{...}" ? kid.type : kid.value);
  }

  private async evaluateQuietly(expression: string, thread?: number, level?: number): Promise<string | undefined> {
    const where = level === undefined ? "" : `--thread ${thread} --frame ${level} `;
    try {
      const r = await this.requireGdb().send(`-data-evaluate-expression ${where}${miQuote(expression)}`);
      return miString(r.results.value);
    } catch {
      return undefined;
    }
  }

  private async setVariable(args: DebugProtocol.SetVariableArguments): Promise<DebugProtocol.SetVariableResponse["body"]> {
    const target = this.assignables.get(args.variablesReference)?.get(args.name);
    if (!target) throw new Error(`Can't set ${args.name}.`);
    const varobj = target.varobj ?? (await this.createVarobj(target.expression!, target.thread, target.level)).name;
    const r = await this.requireGdb().send(`-var-assign ${miQuote(varobj)} ${miQuote(args.value)}`);
    return { value: miString(r.results.value) };
  }

  private async evaluate(args: DebugProtocol.EvaluateArguments): Promise<DebugProtocol.EvaluateResponse["body"]> {
    const gdb = this.requireGdb();
    const text = args.expression.trim();
    // `-exec <gdb command>` (or a leading backquote) in the debug console runs a gdb command
    const raw = /^(?:-exec\s+|`)(.*)$/s.exec(text);
    if (raw && args.context === "repl") {
      const r = await this.console(raw[1]);
      return { result: r.trimEnd(), variablesReference: 0 };
    }
    const frame = args.frameId !== undefined ? this.frames.get(args.frameId) : undefined;
    const where = frame ? `--thread ${frame.thread} --frame ${frame.level} ` : "";
    // gdb's message (`No symbol "x" in current context.`) is the error
    let value = miString((await gdb.send(`-data-evaluate-expression ${where}${miQuote(text)}`)).results.value);
    let type: string | undefined;
    let variablesReference = 0;
    try {
      const v = await this.createVarobj(text, frame?.thread, frame?.level);
      type = v.type;
      if (shapeOf(v.type) === "heap-string") {
        const s = await this.readMylaString(value, frame?.level);
        if (s !== undefined) value = quoteMylaString(s);
      } else if (v.numchild > 0 && isExpandable(v.type, value)) {
        variablesReference = this.addHandle({ kind: "varobj", varobj: v.name, path: text, type: v.type, thread: frame?.thread, level: frame?.level });
      }
    } catch {
      // gdb evaluates it, but can't make a variable object: a plain value
    }
    return { result: value, type, variablesReference };
  }

  /** A gdb CLI command; returns what it printed. */
  private async console(command: string): Promise<string> {
    const r = await this.requireGdb().send(`-interpreter-exec console ${miQuote(command)}`);
    return r.console;
  }

  private requireGdb(): MiTransport {
    if (!this.gdb) throw new Error("gdb isn't running.");
    return this.gdb;
  }
}
