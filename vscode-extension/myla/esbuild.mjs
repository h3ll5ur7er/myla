// Bundles the extension and the standalone debug adapter into out/, with
// vscode-languageclient inlined, so the .vsix needs no node_modules.
//   node esbuild.mjs            one build
//   node esbuild.mjs --watch    rebuild on change
import * as esbuild from "esbuild";

const watch = process.argv.includes("--watch");

const options = {
  entryPoints: {
    extension: "src/extension.ts",
    debugAdapter: "src/debug/adapterMain.ts",
  },
  outdir: "out",
  bundle: true,
  platform: "node",
  format: "cjs",
  // VS Code 1.90 runs extensions on Node 20
  target: "node20",
  external: ["vscode"],
  // a release build is minified; `--watch` keeps it readable, with source maps
  minify: !watch,
  keepNames: true,
  sourcemap: watch ? "linked" : false,
  logLevel: "info",
};

if (watch) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
} else {
  await esbuild.build(options);
}
