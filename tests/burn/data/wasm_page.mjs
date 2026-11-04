// wasm_page.mjs — the page API (tools/wasm/myla.mjs) driven from a test
// (tests/burn/test_wasm.py): `node wasm_page.mjs play.wasm requests.json`
// runs each request `{op: "check"|"run"|"test", files, stdin, args, read}`
// and prints the results as JSON (`read`: files the program wrote, by path).

import { readFileSync } from "node:fs";
import { loadMyla } from "../../../tools/wasm/myla.mjs";

const [wasm, requests] = process.argv.slice(2);
const myla = await loadMyla(readFileSync(wasm));
const out = [];
for (const r of JSON.parse(readFileSync(requests, "utf8"))) {
  if (r.op === "check") {
    out.push(await myla.check(r.files));
  } else {
    const res = r.op === "test" ? await myla.test(r.files) : await myla.run(r.files, { stdin: r.stdin ?? "", args: r.args ?? [] });
    const read = {};
    for (const p of r.read ?? []) read[p] = res.files.text(p) ?? null;
    out.push({ stdout: res.stdout, stderr: res.stderr, exitCode: res.exitCode, read });
  }
}
process.stdout.write(JSON.stringify(out));
