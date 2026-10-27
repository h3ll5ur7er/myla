// Run, test and build the current file: commands that run `myla` tasks (type
// `myla` in tasks.json), whose output the `$myla` problem matcher reads.
import * as path from "node:path";
import * as vscode from "vscode";
import { cliCommandArgs, type MylaCommand, type Toolchain, type ToolMissing } from "./toolchain.ts";

interface MylaTaskDefinition extends vscode.TaskDefinition {
  command: MylaCommand;
  file: string;
  args?: string[];
}

export interface TaskDeps {
  output: vscode.OutputChannel;
  resolveCli: () => Toolchain | ToolMissing;
}

function makeTask(cli: Toolchain, def: MylaTaskDefinition, scope: vscode.WorkspaceFolder | vscode.TaskScope): vscode.Task {
  const name = `${def.command} ${path.basename(def.file)}`;
  const cwd = def.file.includes("${") ? "${fileDirname}" : path.dirname(def.file);
  const task = new vscode.Task(def, scope, name, "myla", new vscode.ProcessExecution(cli.command, cliCommandArgs(cli, def.command, def.file, def.args ?? []), { cwd }), "$myla");
  task.group = def.command === "build" ? vscode.TaskGroup.Build : def.command === "test" ? vscode.TaskGroup.Test : undefined;
  task.presentationOptions = {
    reveal: vscode.TaskRevealKind.Always,
    clear: true,
    // a running program may read its standard input from the terminal
    focus: def.command === "run",
  };
  return task;
}

/** The active editor's .my file, saved. */
async function currentFile(): Promise<vscode.TextDocument | undefined> {
  const doc = vscode.window.activeTextEditor?.document;
  if (!doc || doc.languageId !== "myla") {
    vscode.window.showWarningMessage("Open a Myla (.my) file first.");
    return undefined;
  }
  if (doc.isUntitled) {
    vscode.window.showWarningMessage("Save the Myla file first.");
    return undefined;
  }
  if (doc.isDirty) await doc.save();
  return doc;
}

export function registerTasks(context: vscode.ExtensionContext, deps: TaskDeps): void {
  const cliOrWarn = (): Toolchain | undefined => {
    const cli = deps.resolveCli();
    if ("missing" in cli) {
      deps.output.appendLine(cli.missing);
      vscode.window.showErrorMessage(cli.missing, "Open Settings").then((choice) => {
        if (choice) vscode.commands.executeCommand("workbench.action.openSettings", "myla.cliPath");
      });
      return undefined;
    }
    return cli;
  };

  const runCurrent = async (command: MylaCommand) => {
    const doc = await currentFile();
    const cli = doc && cliOrWarn();
    if (!doc || !cli) return;
    const folder = vscode.workspace.getWorkspaceFolder(doc.uri) ?? vscode.TaskScope.Workspace;
    await vscode.tasks.executeTask(makeTask(cli, { type: "myla", command, file: doc.uri.fsPath }, folder));
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("myla.runFile", () => runCurrent("run")),
    vscode.commands.registerCommand("myla.testFile", () => runCurrent("test")),
    vscode.commands.registerCommand("myla.buildFile", () => runCurrent("build")),
    vscode.tasks.registerTaskProvider("myla", {
      provideTasks: () => {
        const cli = deps.resolveCli();
        if ("missing" in cli) return [];
        const scope = vscode.TaskScope.Workspace;
        return (["run", "test", "build"] as MylaCommand[]).map((command) =>
          makeTask(cli, { type: "myla", command, file: "${file}" }, scope),
        );
      },
      resolveTask: (task) => {
        const def = task.definition as MylaTaskDefinition;
        const cli = deps.resolveCli();
        if ("missing" in cli || !def.command || !def.file) return undefined;
        return makeTask(cli, def, task.scope ?? vscode.TaskScope.Workspace);
      },
    }),
  );
}
