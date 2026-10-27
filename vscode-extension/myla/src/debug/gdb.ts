// A gdb process driven through its MI interpreter: commands go in one at a
// time with a token, results come back as promises, and everything else gdb
// prints (async records, stream records) goes to the listeners.
import { spawn, type ChildProcess } from "node:child_process";
import { parseMiLine, miString, type MiRecord, type MiTuple } from "./mi.ts";

/** A command's result record, with the console output it printed. */
export interface MiResult {
  resultClass: string;
  results: MiTuple;
  console: string;
}

/** gdb answered `^error`. */
export class MiError extends Error {}

/** What the debug session needs from gdb; tests give it a fake. */
export interface MiTransport {
  /** Sends an MI command (without token); rejects with MiError on `^error`. */
  send(command: string): Promise<MiResult>;
  /** Async and stream records that answer no command. */
  onRecord(listener: (record: MiRecord) => void): void;
  /** Every line in and out, for tracing. */
  onTrace(listener: (line: string, direction: "in" | "out") => void): void;
  onExit(listener: (code: number | null) => void): void;
  readonly exited: boolean;
  kill(): void;
}

interface Pending {
  token: number;
  command: string;
  resolve: (r: MiResult) => void;
  reject: (e: Error) => void;
}

export class Gdb implements MiTransport {
  private readonly child: ChildProcess;
  private readonly queue: Pending[] = [];
  private inFlight: Pending | undefined;
  private consoleText = "";
  private nextToken = 1;
  private partial = "";
  private readonly recordListeners: ((r: MiRecord) => void)[] = [];
  private readonly traceListeners: ((line: string, direction: "in" | "out") => void)[] = [];
  private readonly exitListeners: ((code: number | null) => void)[] = [];
  private exitedFlag = false;

  private constructor(child: ChildProcess) {
    this.child = child;
    child.stdout!.setEncoding("utf8").on("data", (chunk: string) => this.onData(chunk));
    // gdb's own complaints, not the program's (its output is redirected)
    child.stderr!.setEncoding("utf8").on("data", (chunk: string) => {
      for (const l of this.recordListeners) l({ kind: "log", text: chunk });
    });
    child.on("exit", (code) => {
      this.exitedFlag = true;
      const err = new MiError("gdb exited");
      for (const p of [...(this.inFlight ? [this.inFlight] : []), ...this.queue.splice(0)]) p.reject(err);
      this.inFlight = undefined;
      for (const l of this.exitListeners) l(code);
    });
  }

  /** Starts `gdb --interpreter=mi3` and waits until it runs. */
  static start(gdbPath: string, cwd: string, env: NodeJS.ProcessEnv = process.env): Promise<Gdb> {
    return new Promise((resolve, reject) => {
      const child = spawn(gdbPath, ["--interpreter=mi3", "--quiet", "--nx"], {
        cwd,
        env,
        stdio: ["pipe", "pipe", "pipe"],
      });
      child.once("error", reject);
      child.once("spawn", () => {
        child.removeListener("error", reject);
        child.on("error", () => {});
        resolve(new Gdb(child));
      });
    });
  }

  get exited(): boolean {
    return this.exitedFlag;
  }

  send(command: string): Promise<MiResult> {
    return new Promise((resolve, reject) => {
      if (this.exitedFlag) {
        reject(new MiError("gdb exited"));
        return;
      }
      this.queue.push({ token: this.nextToken++, command, resolve, reject });
      this.pump();
    });
  }

  onRecord(listener: (record: MiRecord) => void): void {
    this.recordListeners.push(listener);
  }

  onTrace(listener: (line: string, direction: "in" | "out") => void): void {
    this.traceListeners.push(listener);
  }

  onExit(listener: (code: number | null) => void): void {
    this.exitListeners.push(listener);
  }

  kill(): void {
    if (!this.exitedFlag) this.child.kill("SIGKILL");
  }

  private pump(): void {
    if (this.inFlight || this.queue.length === 0) return;
    const next = this.queue.shift()!;
    this.inFlight = next;
    this.consoleText = "";
    const line = `${next.token}${next.command}`;
    for (const l of this.traceListeners) l(line, "out");
    this.child.stdin!.write(line + "\n");
  }

  private onData(chunk: string): void {
    const lines = (this.partial + chunk).split("\n");
    this.partial = lines.pop()!;
    for (const line of lines) this.onLine(line);
  }

  private onLine(line: string): void {
    if (line.trim() === "") return;
    const record = parseMiLine(line);
    if (record.kind === "prompt") return;
    for (const l of this.traceListeners) l(line, "in");
    const pending = this.inFlight;
    if (record.kind === "result" && pending && record.token === pending.token) {
      this.inFlight = undefined;
      if (record.resultClass === "error") pending.reject(new MiError(miString(record.results.msg) || "gdb error"));
      else pending.resolve({ resultClass: record.resultClass, results: record.results, console: this.consoleText });
      this.pump();
      return;
    }
    if (record.kind === "console" && pending) {
      // console output while a command runs belongs to it (e.g. `-exec` commands)
      this.consoleText += record.text;
    }
    for (const l of this.recordListeners) l(record);
  }
}
