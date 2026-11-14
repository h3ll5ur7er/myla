// myla.worker.mjs: the Myla toolchain off the page's thread (MYLA-633, D208).
//
// The page compiles play.wasm once and sends the module ({type: "init",
// module}); then each request {id, op: "check" | "run" | "test", source,
// stdin} is answered with {id, result} (myla.mjs's result) or {id, error}.
// A program that never ends never answers: the page terminates the worker.
// Copied to public/play/worker.mjs beside myla.mjs by scripts/prepare.mjs.

import { Myla } from "./myla.mjs";

let myla = null;
const waiting = [];

self.onmessage = async (event) => {
  const msg = event.data;
  if (msg.type === "init") {
    myla = new Myla(msg.module);
    for (const m of waiting.splice(0)) answer(m);
    return;
  }
  if (!myla) waiting.push(msg);
  else answer(msg);
};

async function answer({ id, op, source, stdin }) {
  try {
    let result;
    if (op === "check") result = await myla.check(source);
    else if (op === "run") result = strip(await myla.run(source, { stdin: stdin ?? "" }));
    else if (op === "test") result = strip(await myla.test(source));
    else throw new Error(`unknown request ${op}`);
    self.postMessage({ id, result });
  } catch (e) {
    self.postMessage({ id, error: String(e?.message ?? e) });
  }
}

// a result without its file system, which can't cross to the page
function strip(r) {
  return { stdout: r.stdout, stderr: r.stderr, exitCode: r.exitCode };
}
