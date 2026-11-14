// check-course.mjs: every exercise as the browser runs it (MYLA-634): through
// play.wasm and tools/wasm/myla.mjs, by the rules of the site's Check button,
// unsolved as given and solved by its solution. tests/burn/test_website.py
// checks the same with the native toolchain; this one checks the toolchain
// the learner actually has (wasm, one worker).
//
//   node scripts/check-course.mjs     (after scripts/prepare.mjs)

import fs from "node:fs";
import path from "node:path";
import { Worker } from "node:worker_threads";
import { fileURLToPath } from "node:url";
import { buildCourse } from "./lib/learn.mjs";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const course = buildCourse(path.resolve(SITE, "../learn"), { byPath: new Set(), byTitle: new Map(), tasks: new Map() });
const LIMIT = 10_000;

// One check in a worker thread of its own, so an endless loop can be stopped.
function run(op, source) {
  return new Promise((resolve) => {
    const w = new Worker(
      `const { parentPort, workerData } = require("node:worker_threads");
       (async () => {
         const { loadMyla } = await import(workerData.api);
         const myla = await loadMyla(require("node:fs").readFileSync(workerData.wasm));
         const r = workerData.op === "test" ? await myla.test(workerData.source) : await myla.run(workerData.source);
         parentPort.postMessage({ stdout: r.stdout, stderr: r.stderr, exitCode: r.exitCode });
       })();`,
      { eval: true, workerData: { op, source, api: new URL("../public/play/myla.mjs", import.meta.url).href, wasm: path.join(SITE, "public/play/play.wasm") } },
    );
    const timer = setTimeout(() => {
      w.terminate();
      resolve({ stdout: "", stderr: "timed out", exitCode: -1 });
    }, LIMIT);
    w.on("message", (r) => {
      clearTimeout(timer);
      w.terminate();
      resolve(r);
    });
    w.on("error", (e) => {
      clearTimeout(timer);
      resolve({ stdout: "", stderr: String(e), exitCode: -1 });
    });
  });
}

async function solved(ex, source) {
  if (ex.mode === "output") {
    const r = await run("run", source);
    return r.exitCode === 0 && r.stdout === ex.expected;
  }
  const r = await run("test", source);
  const m = /(\d+)\/(\d+) passed\./.exec(r.stdout);
  return r.exitCode === 0 && !!m && m[1] === m[2] && +m[2] > 0;
}

let bad = 0;
let n = 0;
for (const ch of course.chapters) {
  for (const ex of ch.exercises) {
    n++;
    const [given, sol] = await Promise.all([solved(ex, ex.starter), solved(ex, ex.solution)]);
    if (given || !sol) {
      bad++;
      console.log(`BAD ${ch.id}/${ex.id}: solved as given ${given}, by its solution ${sol}`);
    }
  }
}
console.log(`check-course: ${n} exercises in play.wasm, ${bad} wrong`);
process.exit(bad ? 1 : 0);
