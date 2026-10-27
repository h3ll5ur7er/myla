// Finding the repository, the myla CLI and expanding path settings
// (src/toolchain.ts). The language server's choice is tested by
// tests/burn/test_lsp.py (TestExtensionStartsTheServer).
import { test } from "node:test";
import assert from "node:assert/strict";
import { chooseCli, cliCommandArgs, expandPath, findCompilerEntry } from "../../src/toolchain.ts";

const exists = (paths: string[]) => (p: string) => paths.includes(p);

test("the CLI: a configured binary, a configured myla.py, the repository's build, python", () => {
  assert.deepEqual(chooseCli({ cliPath: "/opt/myla", compilerEntry: "/r/myla.py" }, exists(["/opt/myla"])), {
    command: "/opt/myla",
    args: [],
  });
  assert.deepEqual(chooseCli({ cliPath: "/src/myla/myla.py", compilerEntry: null }, exists(["/src/myla/myla.py"])), {
    command: "python3",
    args: ["/src/myla/myla.py"],
  });
  assert.deepEqual(chooseCli({ cliPath: "", compilerEntry: "/r/myla.py" }, exists(["/r/build/myla", "/r/myla.py"])), {
    command: "/r/build/myla",
    args: [],
  });
  assert.deepEqual(chooseCli({ cliPath: "", compilerEntry: "/r/myla.py" }, exists(["/r/myla.py"])), {
    command: "python3",
    args: ["/r/myla.py"],
  });
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

test("the compiler entry: a configured root or myla.py, else a workspace folder's", () => {
  const files = exists(["/r/myla.py", "/w2/myla.py"]);
  assert.equal(findCompilerEntry("/r", [], files), "/r/myla.py");
  assert.equal(findCompilerEntry("/r/myla.py", [], files), "/r/myla.py");
  assert.equal(findCompilerEntry("/nope", ["/w2"], files), undefined);
  assert.equal(findCompilerEntry("", ["/w1", "/w2"], files), "/w2/myla.py");
  assert.equal(findCompilerEntry("", ["/w1"], files), undefined);
});

test("path settings expand ~, ${userHome} and ${workspaceFolder}", () => {
  const env = { home: "/home/me", folder: "/work/proj" };
  assert.equal(expandPath("~/bin/myla", env), "/home/me/bin/myla");
  assert.equal(expandPath(" ${workspaceFolder}/build/myla ", env), "/work/proj/build/myla");
  assert.equal(expandPath("${userHome}/x:${userHome}/y", env), "/home/me/x:/home/me/y");
  assert.equal(expandPath("", env), "");
});

test("the command lines of run, test and build", () => {
  const py = { command: "python3", args: ["/r/myla.py"] };
  assert.deepEqual(cliCommandArgs(py, "run", "/w/a.my", ["x"]), ["/r/myla.py", "run", "/w/a.my", "x"]);
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
