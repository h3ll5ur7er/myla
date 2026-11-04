// myla.mjs — Myla in a page (MYLA-158): the checker and the interpreter,
// built for wasm32-wasi from selfhost/play_main.my, behind a small API.
//
//     import { loadMyla } from "./myla.mjs";
//     const myla = await loadMyla(fetch("play.wasm"));   // or bytes, or a Module
//     await myla.check("fun main() { print(1 + true) }")
//         // → { ok: false, diagnostics: [{ severity: "error", kind: "type error",
//         //      message: "…", path: "main.my", line: 1, col: 20, endLine: …, endCol: …, notes: [] }] }
//     await myla.run("fun main() { print(42) }", { stdin: "", args: [] })
//         // → { stdout: "42\n", stderr: "", exitCode: 0, files }
//     await myla.test(source)                             // the #test cases, as `myla test`
//
// `source` is the text of `main.my`, or an object of files (`{"main.my": …,
// "geo.my": …}`) the entry imports from; the standard library is built in.
// Each call runs a fresh instance of the module with its own files in
// memory (`files`: a MemFs, which holds what the program wrote). A program
// that never ends never returns: run it in a Web Worker. A trap (V8's
// "Maximum call stack size exceeded" on deep recursion, say) comes back as
// a runtime error on stderr with exit code 1.

import { Wasi } from "./wasi.mjs";
import { MemFs } from "./mem_fs.mjs";

const ENTRY = "main.my";

export async function loadMyla(source) {
  let module = await source;
  if (typeof Response !== "undefined" && module instanceof Response) module = await WebAssembly.compileStreaming(module);
  else if (!(module instanceof WebAssembly.Module)) module = await WebAssembly.compile(module);
  return new Myla(module);
}

export class Myla {
  constructor(module) {
    this.module = module;
  }

  // `play <args…>` run over `files`: what it printed, its exit code.
  async call(args, files, { stdin = "", env = {} } = {}) {
    const fs = new MemFs(typeof files === "string" ? { [ENTRY]: files } : files);
    const input = new TextEncoder().encode(stdin);
    let at = 0;
    const out = [];
    const err = [];
    const wasi = new Wasi({
      args: ["play", ...args],
      env: { PWD: "/", ...env },
      fs,
      stdin: (u8) => {
        const n = Math.min(u8.length, input.length - at);
        u8.set(input.subarray(at, at + n));
        at += n;
        return n;
      },
      stdout: (u8) => out.push(u8),
      stderr: (u8) => err.push(u8),
    });
    const instance = await WebAssembly.instantiate(this.module, wasi.imports());
    let exitCode;
    let trap = "";
    try {
      exitCode = wasi.start(instance);
    } catch (e) {
      trap = /call stack/i.test(e.message) ? "runtime error: stack overflow\n" : `runtime error: ${e.message}\n`;
      exitCode = 1;
    }
    const text = (chunks) => new TextDecoder().decode(concat(chunks));
    return { stdout: text(out), stderr: text(err) + trap, exitCode, files: fs };
  }

  async check(files) {
    const r = await this.call(["check", ENTRY], files);
    if (r.exitCode > 1) throw new Error(r.stderr || "play check failed");
    return { ok: r.exitCode === 0, diagnostics: JSON.parse(r.stdout) };
  }

  async run(files, { stdin = "", args = [], env = {} } = {}) {
    return this.call(["run", ENTRY, ...args], files, { stdin, env });
  }

  async test(files) {
    return this.call(["test", ENTRY], files);
  }
}

function concat(chunks) {
  const n = chunks.reduce((s, c) => s + c.length, 0);
  const all = new Uint8Array(n);
  let at = 0;
  for (const c of chunks) {
    all.set(c, at);
    at += c.length;
  }
  return all;
}
