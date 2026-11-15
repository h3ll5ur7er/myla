// postbuild.mjs: GitHub Pages answers an unknown path with 404.html, so the
// app is that file too and deep links (/myla/docs/types) work (D208).
import fs from "node:fs";
fs.copyFileSync("dist/index.html", "dist/404.html");
fs.writeFileSync("dist/.nojekyll", "");
