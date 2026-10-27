// A small DAP client for the integration tests: runs the adapter
// (src/debug/adapterMain.ts) as a child process on stdio, sends requests,
// waits for responses and events, and keeps a transcript.
import { spawn, type ChildProcess } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { DebugProtocol } from "@vscode/debugprotocol";
import { encodeMessage, MessageReader } from "../../src/debug/dap.ts";

const EXTENSION = path.resolve(import.meta.dirname, "..", "..");
export const REPO = path.resolve(EXTENSION, "..", "..");
export const FIXTURES = path.join(EXTENSION, "test", "fixtures");

/** The line of `// bp:<name>` in a fixture. */
export function markerLine(file: string, name: string): number {
  const lines = fs.readFileSync(file, "utf8").split("\n");
  const marker = new RegExp(`// bp:${name}\\b`);
  const i = lines.findIndex((l) => marker.test(l));
  if (i < 0) throw new Error(`no marker ${name} in ${file}`);
  return i + 1;
}

/** The myla CLI the tests build with: $MYLA_CLI, the repository's build/myla,
 * else the Python CLI. */
export function testCli(): string {
  if (process.env.MYLA_CLI) return process.env.MYLA_CLI;
  const built = path.join(REPO, "build", "myla");
  return fs.existsSync(built) ? built : path.join(REPO, "myla.py");
}

type Message = DebugProtocol.ProtocolMessage & Record<string, unknown>;

export class DapClient {
  private readonly child: ChildProcess;
  private seq = 1;
  private readonly messages: Message[] = [];
  private readonly waiters: { match: (m: Message) => boolean; resolve: (m: Message) => void }[] = [];
  /** Every message in and out, one JSON line each. */
  readonly transcript: string[] = [];

  constructor() {
    // MYLA_DAP_BUNDLE=1 tests the bundle `npm run build` makes instead of the sources
    const adapter = process.env.MYLA_DAP_BUNDLE
      ? [path.join(EXTENSION, "out", "debugAdapter.js")]
      : ["--experimental-strip-types", "--no-warnings", path.join(EXTENSION, "src", "debug", "adapterMain.ts")];
    this.child = spawn(process.execPath, adapter, { stdio: ["pipe", "pipe", "inherit"] });
    const reader = new MessageReader((m) => this.receive(m as Message));
    this.child.stdout!.on("data", (chunk: Buffer) => reader.push(chunk));
  }

  private receive(m: Message): void {
    this.transcript.push(`<- ${JSON.stringify(m)}`);
    const i = this.waiters.findIndex((w) => w.match(m));
    if (i >= 0) this.waiters.splice(i, 1)[0].resolve(m);
    else this.messages.push(m);
  }

  private next(match: (m: Message) => boolean, what: string, timeout = 20000): Promise<Message> {
    const i = this.messages.findIndex(match);
    if (i >= 0) return Promise.resolve(this.messages.splice(i, 1)[0]);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`timed out waiting for ${what}\n${this.transcript.slice(-15).join("\n")}`)), timeout);
      this.waiters.push({
        match,
        resolve: (m) => {
          clearTimeout(timer);
          resolve(m);
        },
      });
    });
  }

  /** Sends a request and returns its response (success or not). */
  async request<T extends DebugProtocol.Response = DebugProtocol.Response>(command: string, args?: unknown): Promise<T> {
    const seq = this.seq++;
    const message = { seq, type: "request", command, arguments: args };
    this.transcript.push(`-> ${JSON.stringify(message)}`);
    this.child.stdin!.write(encodeMessage(message));
    return (await this.next((m) => m.type === "response" && m.request_seq === seq, `the response to ${command}`)) as unknown as T;
  }

  /** Sends a request that must succeed and returns its body. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async ok(command: string, args?: unknown): Promise<any> {
    const r = await this.request(command, args);
    if (!r.success) throw new Error(`${command} failed: ${r.message}`);
    return r.body;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async event(name: string, timeout?: number): Promise<any> {
    const m = await this.next((x) => x.type === "event" && x.event === name, `the ${name} event`, timeout);
    return m.body ?? {};
  }

  /** All output events so far, of a category. */
  output(category: string): string {
    const out = this.messages
      .filter((m) => m.type === "event" && m.event === "output" && (m.body as { category?: string })?.category === category)
      .map((m) => (m.body as { output: string }).output);
    return out.join("");
  }

  /** initialize, launch, the initialized event. */
  async start(launch: Record<string, unknown>): Promise<DebugProtocol.Response> {
    await this.ok("initialize", { adapterID: "myla", linesStartAt1: true, columnsStartAt1: true, pathFormat: "path" });
    const r = await this.request("launch", { cliPath: testCli(), ...launch });
    if (r.success) await this.event("initialized");
    return r;
  }

  async close(): Promise<void> {
    if (this.child.exitCode === null) {
      await this.request("disconnect", {}).catch(() => undefined);
      await new Promise((resolve) => {
        if (this.child.exitCode !== null) resolve(undefined);
        this.child.once("exit", resolve);
        setTimeout(() => {
          this.child.kill();
          resolve(undefined);
        }, 3000);
      });
    }
  }
}
