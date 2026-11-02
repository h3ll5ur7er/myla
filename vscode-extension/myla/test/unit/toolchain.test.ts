// Finding the repository, the myla CLI and expanding path settings
// (src/toolchain.ts). The language server's choice is tested by
// tests/burn/test_lsp.py (TestExtensionStartsTheServer).
import { test } from "node:test";
import assert from "node:assert/strict";
import { chooseCli, cliCommandArgs, expandPath, findCompilerEntry, repoRootOf } from "../../src/toolchain.ts";

const exists = (paths: string[]) => (p: string) => paths.includes(p);

test("the CLI: a configured binary, else the repository's build", () => {
  assert.deepEqual(chooseCli({ cliPath: "/opt/myla", compilerEntry: "/r/selfhost/main.my" }, exists(["/opt/myla"])), {
    command: "/opt/myla",
    args: [],
  });
  assert.deepEqual(chooseCli({ cliPath: "", compilerEntry: "/r/selfhost/main.my" }, exists(["/r/build/myla"])), {
    command: "/r/build/myla",
    args: [],
  });
  // the Python CLI it fell back to is gone (MYLA-219)
  const unbuilt = chooseCli({ cliPath: "", compilerEntry: "/r/selfhost/main.my" }, exists([]));
  assert.ok("missing" in unbuilt && unbuilt.missing.includes("scripts/bootstrap.sh"));
});

test("a bare command name is looked up on PATH", () => {
  assert.deepEqual(chooseCli({ cliPath: "myla", compilerEntry: undefined }, exists([])), { command: "myla", args: [] });
});

test("no CLI says what to do", () => {
  const none = chooseCli({ cliPath: "", compilerEntry: undefined }, exists([]));
  assert.ok("missing" in none && none.missing.includes("myla.cliPath"));
  const gone = chooseCli({ cliPath: "/opt/nope", compilerEntry: undefined }, exists([]));
  assert.ok("missing" in gone && gone.missing.includes("/opt/nope"));
});

test("the repository's marker: a configured root, or a file in it, else a workspace folder's", () => {
  const files = exists(["/r/selfhost/main.my", "/w2/selfhost/main.my"]);
  assert.equal(findCompilerEntry("/r", [], files), "/r/selfhost/main.my");
  assert.equal(findCompilerEntry("/r/myla.py", [], files), "/r/selfhost/main.my"); // an old setting
  assert.equal(findCompilerEntry("/nope", ["/w2"], files), undefined);
  assert.equal(findCompilerEntry("", ["/w1", "/w2"], files), "/w2/selfhost/main.my");
  assert.equal(findCompilerEntry("", ["/w1"], files), undefined);
  assert.equal(repoRootOf("/w2/selfhost/main.my"), "/w2");
});

test("path settings expand ~, ${userHome} and ${workspaceFolder}", () => {
  const env = { home: "/home/me", folder: "/work/proj" };
  assert.equal(expandPath("~/bin/myla", env), "/home/me/bin/myla");
  assert.equal(expandPath(" ${workspaceFolder}/build/myla ", env), "/work/proj/build/myla");
  assert.equal(expandPath("${userHome}/x:${userHome}/y", env), "/home/me/x:/home/me/y");
  assert.equal(expandPath("", env), "");
});

test("the command lines of run, test and build", () => {
  assert.deepEqual(cliCommandArgs({ command: "/r/build/myla", args: [] }, "run", "/w/a.my", ["x"]), ["run", "/w/a.my", "x"]);
  assert.deepEqual(cliCommandArgs({ command: "myla", args: [] }, "test", "/w/a.my", []), ["test", "/w/a.my"]);
  assert.deepEqual(cliCommandArgs({ command: "myla", args: [] }, "build", "/w/a.my", ["-g"]), ["build", "/w/a.my", "-o", "/w/a", "-g"]);
  assert.deepEqual(cliCommandArgs({ command: "myla", args: [] }, "build", "/w/a.my", ["-o", "/x"]), ["build", "/w/a.my", "-o", "/x"]);
  assert.deepEqual(cliCommandArgs({ command: "myla", args: [] }, "build", "${file}", []), [
    "build",
    "${file}",
    "-o",
    "${fileDirname}/${fileBasenameNoExtension}",
  ]);
});
