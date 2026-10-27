import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";
import { chooseServer } from "./server";

let client: LanguageClient | undefined;
let watcher: vscode.FileSystemWatcher | undefined;
let output: vscode.OutputChannel;

export async function activate(context: vscode.ExtensionContext) {
  output = vscode.window.createOutputChannel("Myla");
  context.subscriptions.push(output);

  context.subscriptions.push(
    vscode.commands.registerCommand("myla.showExtensionInfo", () => {
      vscode.window.showInformationMessage("Myla language support is active.");
    }),
    vscode.commands.registerCommand("myla.restartLanguageServer", async () => {
      await restartServer(context);
    })
  );

  // Restart the server when its configuration changes.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (
        e.affectsConfiguration("myla.serverPath") ||
        e.affectsConfiguration("myla.compilerPath") ||
        e.affectsConfiguration("myla.diagnostics.enable")
      ) {
        await restartServer(context);
      }
    })
  );

  await startServer(context);
}

export function deactivate(): Thenable<void> | undefined {
  watcher?.dispose();
  return client?.stop();
}

async function startServer(context: vscode.ExtensionContext): Promise<void> {
  const config = vscode.workspace.getConfiguration("myla");

  const choice = chooseServer(
    {
      serverPath: expandPath(config.get<string>("serverPath", "")),
      compilerEntry: resolveCompilerEntry(config),
    },
    fs.existsSync
  );
  if ("missing" in choice) {
    output.appendLine(choice.missing);
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

  // The server takes file changes from the editor (didChangeWatchedFiles).
  watcher = vscode.workspace.createFileSystemWatcher("**/*.my");

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
        const enabled = vscode.workspace
          .getConfiguration("myla")
          .get<boolean>("diagnostics.enable", true);
        next(uri, enabled ? diagnostics : []);
      },
    },
  };

  // The id is the settings prefix: vscode-languageclient reads the trace level
  // from `<id>.trace.server`, i.e. `myla.trace.server`.
  client = new LanguageClient(
    "myla",
    "Myla Language Server",
    serverOptions,
    clientOptions
  );

  try {
    await client.start();
    output.appendLine("Myla language server started.");
  } catch (err) {
    output.appendLine(`Failed to start Myla language server: ${err}`);
    vscode.window.showErrorMessage(
      "Could not start the Myla language server. Check 'myla.serverPath' and 'myla.compilerPath', and see the Myla output channel."
    );
    client = undefined;
  }
}

async function restartServer(context: vscode.ExtensionContext): Promise<void> {
  if (client) {
    output.appendLine("Restarting Myla language server...");
    await client.stop();
    client = undefined;
  }
  watcher?.dispose();
  watcher = undefined;
  await startServer(context);
}

/**
 * Resolve the path to the compiler entry point (`myla.py`).
 * `myla.compilerPath` may point at the repo root or directly at `myla.py`.
 * When empty, search each workspace folder for a `myla.py`.
 */
function resolveCompilerEntry(
  config: vscode.WorkspaceConfiguration
): string | undefined {
  const configured = expandPath(config.get<string>("compilerPath", ""));
  if (configured) {
    if (configured.endsWith(".py") && fs.existsSync(configured)) {
      return configured;
    }
    const candidate = path.join(configured, "myla.py");
    if (fs.existsSync(candidate)) {
      return candidate;
    }
    return undefined;
  }

  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    const candidate = path.join(folder.uri.fsPath, "myla.py");
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return undefined;
}

/**
 * A path setting with `${workspaceFolder}` (the first workspace folder),
 * `${userHome}` and a leading `~` expanded, as VS Code does for its own
 * settings but not for an extension's.
 */
function expandPath(value: string): string {
  const home = process.env.HOME ?? process.env.USERPROFILE ?? "";
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";
  let out = value.trim();
  if (out.startsWith("~/")) {
    out = path.join(home, out.slice(2));
  }
  return out
    .replace(/\$\{workspaceFolder\}/g, folder)
    .replace(/\$\{userHome\}/g, home);
}
