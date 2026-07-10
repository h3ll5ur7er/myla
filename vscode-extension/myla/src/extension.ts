import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;
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
    }),
    vscode.commands.registerCommand("myla.formatFile", () => {
      vscode.window.showInformationMessage(
        "Myla formatter is not wired up yet. It will be provided by the language server in a later phase."
      );
    })
  );

  // Restart the server when its configuration changes.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (
        e.affectsConfiguration("myla.pythonPath") ||
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
  return client?.stop();
}

async function startServer(context: vscode.ExtensionContext): Promise<void> {
  const config = vscode.workspace.getConfiguration("myla");

  if (config.get<boolean>("diagnostics.enable", true) === false) {
    output.appendLine(
      "Myla diagnostics are disabled (myla.diagnostics.enable = false)."
    );
    return;
  }

  const entry = resolveCompilerEntry(config);
  if (!entry) {
    const msg =
      "Could not locate the Myla compiler (myla.py). Set 'myla.compilerPath' to the repository root.";
    output.appendLine(msg);
    vscode.window.showWarningMessage(msg);
    return;
  }

  const python = resolvePythonPath(config, entry);

  output.appendLine("Starting Myla language server:");
  output.appendLine(`  python:   ${python}`);
  output.appendLine(`  compiler: ${entry}`);

  const serverOptions: ServerOptions = {
    command: python,
    args: [entry, "lsp"],
    transport: TransportKind.stdio,
    options: { cwd: path.dirname(entry) },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "myla" },
      { scheme: "untitled", language: "myla" },
    ],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.my"),
    },
    outputChannel: output,
  };

  client = new LanguageClient(
    "mylaLanguageServer",
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
      "Could not start the Myla language server. Check 'myla.pythonPath' and 'myla.compilerPath', and see the Myla output channel."
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
  const configured = config.get<string>("compilerPath", "").trim();
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
 * Resolve the Python interpreter. When `myla.pythonPath` is empty, prefer the
 * project's uv-managed `.venv` (which contains pygls) next to `myla.py`, then
 * fall back to `python` on PATH.
 */
function resolvePythonPath(
  config: vscode.WorkspaceConfiguration,
  entry: string
): string {
  const configured = config.get<string>("pythonPath", "").trim();
  if (configured) {
    return configured;
  }

  const repoRoot = path.dirname(entry);
  const venvUnix = path.join(repoRoot, ".venv", "bin", "python");
  const venvWin = path.join(repoRoot, ".venv", "Scripts", "python.exe");
  if (fs.existsSync(venvUnix)) {
    return venvUnix;
  }
  if (fs.existsSync(venvWin)) {
    return venvWin;
  }
  return "python";
}
