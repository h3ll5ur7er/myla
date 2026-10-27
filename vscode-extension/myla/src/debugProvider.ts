// The `myla` debug type in VS Code: configurations (F5 without a launch.json
// debugs the active .my file), the build with -g before each session, and the
// adapter itself, run in the extension host (src/debug/session.ts).
import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import type { DebugProtocol } from "@vscode/debugprotocol";
import { buildCommand, debugOutputPath, debugTarget, runBuild, type CompilerDiagnostic } from "./build.ts";
import { MylaDebugSession } from "./debug/session.ts";
import type { Toolchain, ToolMissing } from "./toolchain.ts";

export interface DebugDeps {
  output: vscode.OutputChannel;
  resolveCli: () => Toolchain | ToolMissing;
  gdbPath: () => string;
}

const CURRENT_FILE: vscode.DebugConfiguration = {
  type: "myla",
  request: "launch",
  name: "Debug current Myla file",
  program: "${file}",
  args: [],
  stopOnEntry: false,
};

/** The adapter in-process: VS Code passes DAP messages straight to it. */
class InlineAdapter implements vscode.DebugAdapter {
  private readonly emitter = new vscode.EventEmitter<vscode.DebugProtocolMessage>();
  readonly onDidSendMessage = this.emitter.event;
  private readonly session = new MylaDebugSession((message) => this.emitter.fire(message));

  handleMessage(message: vscode.DebugProtocolMessage): void {
    this.session.handleMessage(message as DebugProtocol.ProtocolMessage);
  }

  dispose(): void {
    this.session.dispose();
    this.emitter.dispose();
  }
}

const stat = {
  isFile: (p: string) => fs.statSync(p, { throwIfNoEntry: false })?.isFile() ?? false,
  isDirectory: (p: string) => fs.statSync(p, { throwIfNoEntry: false })?.isDirectory() ?? false,
};

async function showBuildError(output: vscode.OutputChannel, message: string, at?: CompilerDiagnostic): Promise<void> {
  const actions = at ? ["Go to Error", "Show Output"] : ["Show Output"];
  const choice = await vscode.window.showErrorMessage(message, ...actions);
  if (choice === "Show Output") output.show(true);
  if (choice === "Go to Error" && at) {
    const doc = await vscode.workspace.openTextDocument(at.file);
    const start = new vscode.Position(at.line - 1, at.column - 1);
    const end = new vscode.Position(at.line - 1, (at.endColumn ?? at.column) - 1);
    await vscode.window.showTextDocument(doc, { selection: new vscode.Range(start, end) });
  }
}

class ConfigurationProvider implements vscode.DebugConfigurationProvider {
  private readonly deps: DebugDeps;
  private readonly buildDir: string;

  constructor(deps: DebugDeps, buildDir: string) {
    this.deps = deps;
    this.buildDir = buildDir;
  }

  provideDebugConfigurations(): vscode.DebugConfiguration[] {
    return [CURRENT_FILE];
  }

  /** F5 without a launch.json: debug the active .my file. */
  resolveDebugConfiguration(
    _folder: vscode.WorkspaceFolder | undefined,
    config: vscode.DebugConfiguration,
  ): vscode.DebugConfiguration | undefined {
    if (!config.type && !config.request && !config.name) {
      if (vscode.window.activeTextEditor?.document.languageId !== "myla") {
        vscode.window.showErrorMessage("Open a Myla (.my) file to debug it, or add a 'myla' launch configuration.");
        return undefined;
      }
      return { ...CURRENT_FILE };
    }
    if (!config.program) {
      vscode.window.showErrorMessage("The Myla launch configuration needs a 'program': the .my file to debug.");
      return undefined;
    }
    return config;
  }

  /** Builds the program with -g; a failed build stops the launch. */
  async resolveDebugConfigurationWithSubstitutedVariables(
    folder: vscode.WorkspaceFolder | undefined,
    config: vscode.DebugConfiguration,
  ): Promise<vscode.DebugConfiguration | undefined> {
    const base = folder?.uri.fsPath ?? path.dirname(vscode.window.activeTextEditor?.document.uri.fsPath ?? process.cwd());
    const program = path.resolve(base, config.program);
    config.program = program;
    config.cwd = config.cwd ? path.resolve(base, config.cwd) : (folder?.uri.fsPath ?? path.dirname(program));
    config.gdbPath ||= this.deps.gdbPath();
    if (config.executable) return config;

    const target = debugTarget(program, stat);
    if (target.kind === "missing") {
      vscode.window.showErrorMessage(target.message);
      return undefined;
    }
    if (target.kind === "binary") {
      config.executable = target.path;
      return config;
    }
    const file = target.kind === "file" ? target.file : target.main;
    const cli = this.deps.resolveCli();
    if ("missing" in cli) {
      await showBuildError(this.deps.output, cli.missing);
      return undefined;
    }
    // build what the editor shows
    for (const doc of vscode.workspace.textDocuments) {
      if (doc.isDirty && doc.languageId === "myla" && !doc.isUntitled) await doc.save();
    }
    fs.mkdirSync(this.buildDir, { recursive: true });
    const executable = debugOutputPath(this.buildDir, file);
    const command = buildCommand(cli, file, executable, true);
    this.deps.output.appendLine(`Building for the debugger: ${[command.command, ...command.args].join(" ")}`);
    const result = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Window, title: `Myla: building ${path.basename(file)} with -g` },
      () => runBuild(command, path.dirname(file)),
    );
    if (result.output) this.deps.output.append(result.output);
    if (!result.ok) {
      const first = result.diagnostics[0];
      const where = first ? ` (${path.basename(first.file)}:${first.line})` : "";
      const message = first ? `${first.message}${where}` : result.output.trim().split("\n")[0] || "the build failed";
      await showBuildError(this.deps.output, `Myla: can't debug ${path.basename(file)}: ${message}`, first);
      return undefined;
    }
    config.executable = executable;
    return config;
  }
}

/** One configuration for the active file in the Run and Debug view's list. */
class DynamicProvider implements vscode.DebugConfigurationProvider {
  provideDebugConfigurations(): vscode.DebugConfiguration[] {
    const doc = vscode.window.activeTextEditor?.document;
    if (doc?.languageId !== "myla" || doc.isUntitled) return [];
    return [{ ...CURRENT_FILE, name: `Debug ${path.basename(doc.uri.fsPath)}`, program: doc.uri.fsPath }];
  }
}

export function registerDebugger(context: vscode.ExtensionContext, deps: DebugDeps): void {
  const storage = context.storageUri ?? context.globalStorageUri;
  const buildDir = path.join(storage.fsPath, "debug-builds");
  context.subscriptions.push(
    vscode.debug.registerDebugConfigurationProvider("myla", new ConfigurationProvider(deps, buildDir)),
    vscode.debug.registerDebugConfigurationProvider(
      "myla",
      new DynamicProvider(),
      vscode.DebugConfigurationProviderTriggerKind.Dynamic,
    ),
    vscode.debug.registerDebugAdapterDescriptorFactory("myla", {
      createDebugAdapterDescriptor: () => new vscode.DebugAdapterInlineImplementation(new InlineAdapter()),
    }),
    vscode.commands.registerCommand("myla.debugFile", async () => {
      const doc = vscode.window.activeTextEditor?.document;
      if (doc?.languageId !== "myla" || doc.isUntitled) {
        vscode.window.showWarningMessage("Open a saved Myla (.my) file to debug it.");
        return;
      }
      await vscode.debug.startDebugging(vscode.workspace.getWorkspaceFolder(doc.uri), {
        ...CURRENT_FILE,
        name: `Debug ${path.basename(doc.uri.fsPath)}`,
        program: doc.uri.fsPath,
      });
    }),
  );
}
