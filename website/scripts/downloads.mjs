// downloads.mjs: the tools of a master build in the deployed site
// (MYLA-635): the CI's tarballs and the VS Code extension, under stable
// names in <site>/downloads, with manifest.json for the download page.
//
//   node scripts/downloads.mjs <artifacts dir> <site>/downloads <commit>

import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const [from, to, commit] = process.argv.slice(2);
if (!from || !to || !commit) {
  console.error("usage: node scripts/downloads.mjs <artifacts dir> <downloads dir> <commit>");
  process.exit(2);
}

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]));
}

const platformOf = (name) =>
  name.includes("x86_64-linux") ? "x86_64-linux" : name.includes("aarch64-linux") ? "aarch64-linux" : name.endsWith(".vsix") ? "vscode" : null;

fs.mkdirSync(to, { recursive: true });
const files = [];
for (const f of fs.existsSync(from) ? walk(from) : []) {
  const base = path.basename(f);
  const platform = platformOf(base);
  if (!platform) continue;
  const name = platform === "vscode" ? "myla-vscode.vsix" : `myla-${platform}.tar.gz`;
  fs.copyFileSync(f, path.join(to, name));
  const bytes = fs.readFileSync(f);
  files.push({ name, platform, size: bytes.length, sha256: crypto.createHash("sha256").update(bytes).digest("hex") });
}
const manifest = { commit, date: new Date().toISOString().slice(0, 10), files };
fs.writeFileSync(path.join(to, "manifest.json"), JSON.stringify(manifest, null, 2));
console.log(`downloads: ${files.map((f) => f.name).join(", ") || "none"}`);
