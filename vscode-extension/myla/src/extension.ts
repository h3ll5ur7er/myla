// The Myla extension: starts the language server, offers run/test/build
// commands and tasks, and registers the gdb debugger.
import * as fs from "node:fs";
import * as os from "node:os";
import * as vscode from "vscode";
import { LanguageClient, TransportKind, type LanguageClientOptions, type ServerOptions } from "vscode-languageclient/node";
import { registerDebugger } from "./debugProvider.ts";
import { chooseServer } from "./server.ts";
import { registerTasks } from "./tasks.ts";
import { chooseCli, expandPath, findCompilerEntry, type Toolchain, type ToolMissing } from "./toolchain.ts";

let client: LanguageClient | undefined;
let watcher: vscode.FileSystemWatcher | undefined;
let output: vscode.LogOutputChannel;
let status: vscode.LanguageStatusItem;

/** A path setting, expanded. */
function pathSetting(name: string): string {
  const value = vscode.workspace.getConfiguration("myla").get<string>(name, "");
  return expandPath(value, {
    home: os.homedir(),
    folder: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "",
  });
}

/** The repository's myla.py, which marks its root. */
function compilerEntry(): string | undefined {
  const folders = (vscode.workspace.workspaceFolders ?? []).map((f) => f.uri.fsPath);
  return findCompilerEntry(pathSetting("compilerPath"), folders, fs.existsSync);
}

/** The myla CLI from the settings and the repository. */
export function resolveCli(): Toolchain | ToolMissing {
  return chooseCli({ cliPath: pathSetting("cliPath"), compilerEntry: compilerEntry() }, fs.existsSync);
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  // a log channel: vscode-languageclient 10 writes its own log lines to it
  output = vscode.window.createOutputChannel("Myla", { log: true });
  status = vscode.languages.createLanguageStatusItem("myla.languageServer", { language: "myla" });
  status.name = "Myla language server";
  context.subscriptions.push(output, status);

  context.subscriptions.push(
    vscode.commands.registerCommand("myla.restartLanguageServer", () => restartServer()),
    vscode.commands.registerCommand("myla.showOutput", () => output.show()),
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (
        e.affectsConfiguration("myla.serverPath") ||
        e.affectsConfiguration("myla.compilerPath") ||
        e.affectsConfiguration("myla.diagnostics.enable")
      ) {
        await restartServer();
      }
    }),
  );
  registerTasks(context, { output, resolveCli });
  registerDebugger(context, {
    output,
    resolveCli,
    gdbPath: () => vscode.workspace.getConfiguration("myla").get<string>("debug.gdbPath", "gdb") || "gdb",
  });

  await startServer();
}

export function deactivate(): Thenable<void> | undefined {
  watcher?.dispose();
  return client?.stop();
}

function showStatus(text: string, detail: string, severity: vscode.LanguageStatusSeverity): void {
  status.text = text;
  status.detail = detail;
  status.severity = severity;
  status.command = { title: "Restart", command: "myla.restartLanguageServer" };
}

async function startServer(): Promise<void> {
  const choice = chooseServer({ serverPath: pathSetting("serverPath"), compilerEntry: compilerEntry() }, fs.existsSync);
  if ("missing" in choice) {
    output.appendLine(choice.missing);
    showStatus("Myla: no language server", choice.missing, vscode.LanguageStatusSeverity.Warning);
    vscode.window.showWarningMessage(choice.missing);
    return;
  }

  output.appendLine("Starting the Myla language server:");
  output.appendLine(`  ${[choice.command, ...choice.args].join(" ")}`);

  const serverOptions: ServerOptions = {
    command: choice.command,
    args: choice.args,
    transport: TransportKind.stdio,
    options: { cwd: choice.cwd },
  };

  // The server takes file changes from the editor (didChangeWatchedFiles):
  // sources, and the manifests and lock files of projects (MYLA-97).
  watcher = vscode.workspace.createFileSystemWatcher("**/{*.my,myla.toml,myla.lock}");

  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "myla" },
      { scheme: "untitled", language: "myla" },
    ],
    outputChannel: output,
    synchronize: { fileEvents: watcher },
    middleware: {
      // `myla.diagnostics.enable = false` hides the diagnostics only; hover,
      // definition and the rest keep working.
      handleDiagnostics: (uri, diagnostics, next) => {
        const enabled = vscode.workspace.getConfiguration("myla").get<boolean>("diagnostics.enable", true);
        next(uri, enabled ? diagnostics : []);
      },
    },
  };

  // The id is the settings prefix: vscode-languageclient reads the trace level
  // from `<id>.trace.server`, i.e. `myla.trace.server`.
  client = new LanguageClient("myla", "Myla Language Server", serverOptions, clientOptions);

  try {
    await client.start();
    output.appendLine("Myla language server started.");
    showStatus("Myla", `Language server: ${choice.command}`, vscode.LanguageStatusSeverity.Information);
  } catch (err) {
    output.appendLine(`Failed to start Myla language server: ${err}`);
    showStatus("Myla: language server failed", String(err), vscode.LanguageStatusSeverity.Error);
    vscode.window.showErrorMessage(
      "Could not start the Myla language server. Check 'myla.serverPath' and 'myla.compilerPath', and see the Myla output channel.",
    );
    client = undefined;
  }
}

async function restartServer(): Promise<void> {
  if (client) {
    output.appendLine("Restarting the Myla language server...");
    await client.stop();
    client = undefined;
  }
  watcher?.dispose();
  watcher = undefined;
  await startServer();
}
