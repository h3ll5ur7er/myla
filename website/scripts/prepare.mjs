// prepare.mjs: what the website needs from the rest of the repository,
// generated before `ng build` and `ng serve` (D208):
//
//   public/play/      play.wasm (the checker and interpreter, MYLA-158), the
//                     page API and WASI shim (tools/wasm/*.mjs), the worker
//   public/content/   the docs, the reference and the course (content.mjs)
//
// It uses the toolchain of scripts/bootstrap.sh (build/myla, or $MYLA).
//
//   node scripts/prepare.mjs [--skip-wasm]

import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { buildContent, REPO_ROOT } from "./content.mjs";

const SITE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MYLA = process.env.MYLA ?? path.join(REPO_ROOT, "build", "myla");
const BUILD = path.join(REPO_ROOT, "build", "website");
const skipWasm = process.argv.includes("--skip-wasm");

if (!fs.existsSync(MYLA)) {
  console.error(`prepare: no Myla toolchain at ${MYLA}: run scripts/bootstrap.sh first (or set MYLA)`);
  process.exit(1);
}

function myla(args) {
  execFileSync(MYLA, args, { cwd: REPO_ROOT, stdio: ["ignore", "inherit", "inherit"] });
}

const t0 = Date.now();
fs.mkdirSync(BUILD, { recursive: true });

// --- the toolchain in the page --------------------------------------------------------
const play = path.join(SITE, "public", "play");
fs.mkdirSync(play, { recursive: true });
if (!skipWasm || !fs.existsSync(path.join(play, "play.wasm"))) {
  myla(["build", "selfhost/play_main.my", "--target", "wasm32-wasi", "-o", path.join(play, "play.wasm")]);
}
for (const f of ["myla.mjs", "wasi.mjs", "mem_fs.mjs"]) fs.copyFileSync(path.join(REPO_ROOT, "tools", "wasm", f), path.join(play, f));
fs.copyFileSync(path.join(SITE, "src", "worker", "myla.worker.mjs"), path.join(play, "worker.mjs"));

// --- the API reference ------------------------------------------------------------------
const doc = path.join(BUILD, "doc");
myla(["build", "tools/doc/main.my", "-o", doc]);
const internal = new Set(["rt", "platform", "platform_aarch64", "platform_wasm", "slice"]);
const modules = fs
  .readdirSync(path.join(REPO_ROOT, "lib", "std"))
  .filter((f) => f.endsWith(".my") && !internal.has(f.replace(/\.my$/, "")))
  .sort()
  .map((f) => path.join("lib", "std", f));
const api = path.join(BUILD, "api.json");
execFileSync(doc, ["-o", api, ...modules], { cwd: REPO_ROOT, stdio: ["ignore", "inherit", "inherit"] });

// --- the content -------------------------------------------------------------------------
const out = path.join(SITE, "public", "content");
fs.rmSync(out, { recursive: true, force: true });
const stats = buildContent(api, out);
console.log(`prepare: ${stats.docs} docs pages, ${stats.modules} modules, ${stats.chapters} chapters (${stats.exercises} exercises), ${stats.search} search entries, in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
