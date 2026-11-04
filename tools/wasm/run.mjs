// run.mjs — runs a Myla program built for wasm32-wasi under Node, through
// the WASI shim of wasi.mjs over the host's files (MYLA-158):
//
//     node tools/wasm/run.mjs program.wasm [args…]
//
// The program sees the host's `/` as its root, the working directory as
// `PWD`, the environment and the arguments (the module's path first); its
// exit code is the process's. A trap (a wasm runtime error the program
// didn't report itself) ends it with 134 and the engine's message.

import { readFileSync } from "node:fs";
import { Wasi } from "./wasi.mjs";
import { NodeFs, nodeStdio } from "./node_fs.mjs";

const [file, ...rest] = process.argv.slice(2);
if (!file) {
  process.stderr.write("usage: node run.mjs program.wasm [args…]\n");
  process.exit(2);
}
const wasi = new Wasi({ args: [file, ...rest], env: { ...process.env, PWD: process.cwd() }, fs: new NodeFs(), ...nodeStdio });
const module = new WebAssembly.Module(readFileSync(file));
const instance = new WebAssembly.Instance(module, wasi.imports());
let code;
try {
  code = wasi.start(instance);
} catch (e) {
  process.stderr.write(`wasm trap: ${e.message}\n`);
  code = 134;
}
process.exitCode = code;
