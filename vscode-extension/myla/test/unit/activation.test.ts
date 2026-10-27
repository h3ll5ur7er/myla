// The bundled extension (out/extension.js) activates against a stand-in for
// the `vscode` module and registers everything package.json contributes:
// every command, the task provider, the debug configuration providers and the
// debug adapter. Catches bundling mistakes and ids that don't match the
// manifest. Skipped until `npm run build` has made the bundle.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import Module, { createRequire } from "node:module";

const EXTENSION = path.resolve(import.meta.dirname, "..", "..");
const BUNDLE = path.join(EXTENSION, "out", "extension.js");
const manifest = JSON.parse(fs.readFileSync(path.join(EXTENSION, "package.json"), "utf8"));

interface Recorded {
  commands: string[];
  taskProviders: string[];
  configProviders: [string, unknown][];
  adapterFactories: string[];
  warnings: string[];
}

/** Anything: callable, constructible, with any property. */
function anything(): unknown {
  const fn = function () {};
  return new Proxy(fn, {
    get: (_t, prop) => (prop === Symbol.toPrimitive ? () => "" : prop === "then" ? undefined : anything()),
    apply: () => anything(),
    construct: () => anything() as object,
  });
}

function fakeVscode(rec: Recorded): unknown {
  const disposable = { dispose() {} };
  const api = {
    window: {
      createOutputChannel: () => ({ appendLine() {}, append() {}, show() {}, dispose() {} }),
      showWarningMessage: async (m: string) => void rec.warnings.push(m),
      showErrorMessage: async (m: string) => void rec.warnings.push(m),
      activeTextEditor: undefined,
    },
    languages: { createLanguageStatusItem: () => ({ dispose() {} }) },
    LanguageStatusSeverity: { Information: 0, Warning: 1, Error: 2 },
    commands: {
      registerCommand: (id: string) => {
        rec.commands.push(id);
        return disposable;
      },
    },
    workspace: {
      workspaceFolders: [],
      getConfiguration: () => ({ get: (_k: string, d: unknown) => d }),
      onDidChangeConfiguration: () => disposable,
      createFileSystemWatcher: () => disposable,
      textDocuments: [],
    },
    tasks: {
      registerTaskProvider: (type: string) => {
        rec.taskProviders.push(type);
        return disposable;
      },
    },
    debug: {
      registerDebugConfigurationProvider: (type: string, _p: unknown, trigger?: unknown) => {
        rec.configProviders.push([type, trigger]);
        return disposable;
      },
      registerDebugAdapterDescriptorFactory: (type: string) => {
        rec.adapterFactories.push(type);
        return disposable;
      },
    },
    DebugConfigurationProviderTriggerKind: { Initial: 1, Dynamic: 2 },
  };
  return new Proxy(api, { get: (t, prop) => (prop in t ? t[prop as keyof typeof t] : anything()) });
}

test("the bundle activates and registers what package.json contributes", { skip: !fs.existsSync(BUNDLE) && "run npm run build first" }, async () => {
  const rec: Recorded = { commands: [], taskProviders: [], configProviders: [], adapterFactories: [], warnings: [] };
  const vscode = fakeVscode(rec);
  // hand the bundle our `vscode` when it requires it
  const original = (Module as unknown as { _load: (...a: unknown[]) => unknown })._load;
  (Module as unknown as { _load: (...a: unknown[]) => unknown })._load = function (request: unknown, ...rest: unknown[]) {
    return request === "vscode" ? vscode : original.call(this, request, ...rest);
  };
  try {
    const ext = createRequire(import.meta.url)(BUNDLE);
    const context = {
      subscriptions: [] as unknown[],
      storageUri: undefined,
      globalStorageUri: { fsPath: "/tmp/myla-test-storage" },
    };
    await ext.activate(context);
    const contributed = manifest.contributes.commands.map((c: { command: string }) => c.command).sort();
    assert.deepEqual([...new Set(rec.commands)].sort(), contributed);
    assert.deepEqual(rec.taskProviders, ["myla"]);
    assert.deepEqual(
      rec.configProviders.map(([type]) => type),
      ["myla", "myla"],
    );
    assert.deepEqual(rec.adapterFactories, ["myla"]);
    // the debug type and task type match the manifest
    assert.equal(manifest.contributes.debuggers[0].type, "myla");
    assert.equal(manifest.contributes.taskDefinitions[0].type, "myla");
    // no repository in the workspace: it says how to get a language server
    assert.ok(rec.warnings.some((w) => w.includes("myla.serverPath")), rec.warnings.join("\n"));
    assert.ok(context.subscriptions.length > 0);
  } finally {
    (Module as unknown as { _load: unknown })._load = original;
  }
});

test("the manifest's activation events and contributions are consistent", () => {
  const events: string[] = manifest.activationEvents;
  // VS Code derives onLanguage and onCommand events from the contributions
  assert.ok(!events.some((e) => e.startsWith("onLanguage:") || e.startsWith("onCommand:")), events.join(", "));
  assert.ok(manifest.contributes.breakpoints.some((b: { language: string }) => b.language === "myla"));
  const debuggerType = manifest.contributes.debuggers[0];
  assert.deepEqual(debuggerType.languages, ["myla"]);
  assert.deepEqual(debuggerType.configurationAttributes.launch.required, ["program"]);
  // every command the menus name exists
  const commands = new Set(manifest.contributes.commands.map((c: { command: string }) => c.command));
  for (const items of Object.values(manifest.contributes.menus) as { command: string }[][]) {
    for (const item of items) assert.ok(commands.has(item.command), item.command);
  }
  // the files the manifest points at exist
  for (const file of [manifest.icon, ...manifest.contributes.grammars.map((g: { path: string }) => g.path), ...manifest.contributes.snippets.map((s: { path: string }) => s.path), manifest.contributes.languages[0].configuration]) {
    assert.ok(fs.existsSync(path.join(EXTENSION, file)), file);
  }
});
