// serve.mjs: the built site as GitHub Pages serves it, for the end-to-end
// tests and a look before deploying (MYLA-635): files from dist/ under a
// base path, and the app (404.html) for any other path, so deep links work.
//
//   node scripts/serve.mjs [--port 4300] [--base /myla/] [--dir dist]

import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : dflt;
};
const port = Number(arg("--port", "4300"));
const base = arg("--base", "/");
const dir = path.resolve(arg("--dir", "dist"));
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".wasm": "application/wasm", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".woff": "font/woff", ".ico": "image/x-icon", ".png": "image/png", ".gz": "application/gzip", ".vsix": "application/octet-stream" };

http
  .createServer((req, res) => {
    const url = new URL(req.url, "http://x");
    if (!url.pathname.startsWith(base)) {
      res.writeHead(302, { location: base });
      return res.end();
    }
    const rel = decodeURIComponent(url.pathname.slice(base.length));
    let file = path.join(dir, rel);
    if (!file.startsWith(dir)) {
      res.writeHead(403);
      return res.end();
    }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
    let status = 200;
    if (!fs.existsSync(file)) {
      file = path.join(dir, "404.html");
      status = 404;
    }
    res.writeHead(status, { "content-type": TYPES[path.extname(file)] ?? "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  })
  .listen(port, () => console.log(`serving ${dir} at http://localhost:${port}${base}`));
