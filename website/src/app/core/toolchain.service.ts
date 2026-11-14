import { Injectable, signal } from '@angular/core';

// The Myla toolchain in the browser (MYLA-633, D208): play.wasm, the
// self-hosted checker and interpreter built for wasm32-wasi (MYLA-158),
// compiled once on first use and shared with Web Workers. Checks go to one
// worker that lives on; each run or test gets a worker of its own, which a
// stop or the time limit terminates, so a program that never ends stops.

export interface Diagnostic {
  severity: 'error' | 'warning';
  kind: string;
  message: string;
  path: string;
  line: number;
  col: number;
  endLine: number;
  endCol: number;
  notes: { label: string; message: string; line: number; col: number }[];
}

export interface CheckResult {
  ok: boolean;
  diagnostics: Diagnostic[];
}

export interface RunResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  ms: number;
  timedOut?: boolean;
  stopped?: boolean;
}

export interface RunHandle {
  result: Promise<RunResult>;
  stop(): void;
}

export type ToolchainStatus = 'idle' | 'loading' | 'ready' | 'failed';

type Op = 'check' | 'run' | 'test';

interface Pending {
  resolve(v: unknown): void;
  reject(e: Error): void;
}

export const DEFAULT_TIMEOUT_MS = 10_000;

// What a worker answers.
interface Reply {
  id: number;
  result?: unknown;
  error?: string;
}

@Injectable({ providedIn: 'root' })
export class ToolchainService {
  readonly status = signal<ToolchainStatus>('idle');
  private module: Promise<WebAssembly.Module> | null = null;
  private checker: Worker | null = null;
  private pending = new Map<number, Pending>();
  private nextId = 1;

  // play.wasm compiled, once.
  load(): Promise<WebAssembly.Module> {
    if (!this.module) {
      this.status.set('loading');
      const url = new URL('play/play.wasm', document.baseURI).href;
      this.module = (async () => {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`play.wasm: ${res.status}`);
        try {
          return await WebAssembly.compileStreaming(res.clone());
        } catch {
          // a server without the wasm content type
          return await WebAssembly.compile(await res.arrayBuffer());
        }
      })();
      this.module.then(
        () => this.status.set('ready'),
        () => {
          this.status.set('failed');
          this.module = null;
        },
      );
    }
    return this.module;
  }

  private async spawn(): Promise<Worker> {
    const module = await this.load();
    const w = new Worker(new URL('play/worker.mjs', document.baseURI), { type: 'module' });
    w.postMessage({ type: 'init', module });
    return w;
  }

  // The diagnostics of `source` (the errors as `myla check` reports them,
  // then the warnings).
  async check(source: string): Promise<CheckResult> {
    if (!this.checker) {
      const w = await this.spawn();
      if (!this.checker) {
        this.checker = w;
        w.onmessage = (e: MessageEvent<Reply>) => this.settle(e.data);
        w.onerror = () => this.resetChecker(new Error('the checker stopped'));
      } else {
        w.terminate();
      }
    }
    const id = this.nextId++;
    return new Promise<CheckResult>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
      this.checker!.postMessage({ id, op: 'check', source });
    });
  }

  private settle(r: Reply): void {
    const p = this.pending.get(r.id);
    if (!p) return;
    this.pending.delete(r.id);
    if (r.error !== undefined) p.reject(new Error(r.error));
    else p.resolve(r.result);
  }

  private resetChecker(e: Error): void {
    this.checker?.terminate();
    this.checker = null;
    for (const p of this.pending.values()) p.reject(e);
    this.pending.clear();
  }

  run(source: string, opts: { stdin?: string; timeoutMs?: number } = {}): RunHandle {
    return this.exec('run', source, opts);
  }

  // The #test cases, as `myla test` runs them.
  test(source: string, opts: { timeoutMs?: number } = {}): RunHandle {
    return this.exec('test', source, opts);
  }

  private exec(op: Op, source: string, opts: { stdin?: string; timeoutMs?: number }): RunHandle {
    let worker: Worker | null = null;
    let finish: ((r: RunResult) => void) | null = null;
    let done = false;
    const t0 = performance.now();
    const end = (r: RunResult) => {
      if (done) return;
      done = true;
      worker?.terminate();
      finish?.(r);
    };
    const result = new Promise<RunResult>((resolve, reject) => {
      finish = resolve;
      this.spawn().then(
        (w) => {
          if (done) {
            w.terminate();
            return;
          }
          worker = w;
          const timer = setTimeout(
            () => end({ stdout: '', stderr: '', exitCode: -1, ms: performance.now() - t0, timedOut: true }),
            opts.timeoutMs ?? DEFAULT_TIMEOUT_MS,
          );
          w.onmessage = (e: MessageEvent<Reply>) => {
            clearTimeout(timer);
            if (e.data.error !== undefined) {
              done = true;
              w.terminate();
              reject(new Error(e.data.error));
            } else {
              end({ ...(e.data.result as Omit<RunResult, 'ms'>), ms: performance.now() - t0 });
            }
          };
          w.onerror = (e) => {
            clearTimeout(timer);
            done = true;
            w.terminate();
            reject(new Error(e.message || 'the program could not start'));
          };
          w.postMessage({ id: 1, op, source, stdin: opts.stdin ?? '' });
        },
        (e) => {
          done = true;
          reject(e);
        },
      );
    });
    return {
      result,
      stop: () => end({ stdout: '', stderr: '', exitCode: -1, ms: performance.now() - t0, stopped: true }),
    };
  }
}

// The counts of a `myla test` summary line, `5/6 passed.`; null without one.
export function testSummary(stdout: string): { passed: number; total: number } | null {
  const m = /(\d+)\/(\d+) passed\./.exec(stdout);
  return m ? { passed: +m[1], total: +m[2] } : null;
}
