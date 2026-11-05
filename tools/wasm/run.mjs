// run.mjs — runs a Myla program built for wasm32-wasi under Node, through
// the WASI shim of wasi.mjs over the host's files (MYLA-158):
//
//     node tools/wasm/run.mjs program.wasm [args…]
//
// The program sees the host's `/` as its root, the working directory as
// `PWD`, the environment and the arguments (the module's path first); its
// exit code is the process's. A trap the program didn't report itself ends
// it as a runtime error does natively: the engine's call stack running out
// as `runtime error: stack overflow`, anything else as `runtime error:
// <the engine's message>`, with exit code 1 (MYLA-261, as myla.mjs).

import { readFileSync } from "node:fs";
import { Wasi } from "./wasi.mjs";
import { NodeFs, nodeStdio } from "./node_fs.mjs";

// `--argv0 NAME` first: the name the program sees as its argv[0] (the test
// harness gives the native binaries' one, MYLA-268), else the file's.
let given = process.argv.slice(2);
let argv0 = null;
if (given[0] === "--argv0" && given.length >= 2) {
  argv0 = given[1];
  given = given.slice(2);
}
const [file, ...rest] = given;
if (!file) {
  process.stderr.write("usage: node run.mjs program.wasm [args…]\n");
  process.exit(2);
}
const wasi = new Wasi({ args: [argv0 ?? file, ...rest], env: { ...process.env, PWD: process.cwd() }, fs: new NodeFs(), ...nodeStdio });
const module = new WebAssembly.Module(readFileSync(file));
const instance = new WebAssembly.Instance(module, wasi.imports());
let code;
try {
  code = wasi.start(instance);
} catch (e) {
  if (!(e instanceof WebAssembly.RuntimeError || e instanceof RangeError)) throw e;
  process.stderr.write(/call stack/i.test(e.message) ? "runtime error: stack overflow\n" : `runtime error: ${e.message}\n`);
  code = 1;
}
process.exitCode = code;
