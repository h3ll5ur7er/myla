// Where the Myla tools are: the repository, the `myla` CLI, and path
// settings. Needs nothing from VS Code, so node runs its tests directly.
import * as path from "node:path";

/** A command line prefix: `command ...args` followed by e.g. `run file.my`. */
export interface Toolchain {
  command: string;
  args: string[];
}

/** Why there is no tool to run. */
export interface ToolMissing {
  missing: string;
}

/**
 * A path setting with a leading `~`, `${userHome}` and `${workspaceFolder}`
 * (the first workspace folder) expanded, as VS Code does for its own settings
 * but not for an extension's.
 */
export function expandPath(value: string, env: { home: string; folder: string }): string {
  let out = value.trim();
  if (out === "~" || out.startsWith("~/")) out = path.join(env.home, out.slice(1));
  return out.replace(/\$\{workspaceFolder\}/g, env.folder).replace(/\$\{userHome\}/g, env.home);
}

/**
 * The repository's `myla.py`, which marks its root: `myla.compilerPath` (the
 * root or `myla.py` itself), else the first workspace folder that has one.
 */
export function findCompilerEntry(
  configured: string,
  workspaceFolders: string[],
  exists: (p: string) => boolean,
): string | undefined {
  if (configured) {
    if (configured.endsWith(".py")) return exists(configured) ? configured : undefined;
    const candidate = path.join(configured, "myla.py");
    return exists(candidate) ? candidate : undefined;
  }
  for (const folder of workspaceFolders) {
    const candidate = path.join(folder, "myla.py");
    if (exists(candidate)) return candidate;
  }
  return undefined;
}

/** A `.py` path runs with python3, anything else is the program itself. */
function asCommand(cli: string): Toolchain {
  return cli.endsWith(".py") ? { command: "python3", args: [cli] } : { command: cli, args: [] };
}

/**
 * The `myla` CLI for run, test, build and debug builds: `myla.cliPath`, else
 * the self-hosted `build/myla` of the repository (built by
 * `scripts/bootstrap.sh`), else the Python CLI `python3 myla.py`.
 */
export function chooseCli(
  settings: { cliPath: string; compilerEntry: string | null | undefined },
  exists: (p: string) => boolean,
): Toolchain | ToolMissing {
  const configured = settings.cliPath;
  if (configured) {
    // a bare name such as `myla` is looked up on PATH when it runs
    if (!configured.includes("/") || exists(configured)) return asCommand(configured);
    return { missing: `The myla CLI set in 'myla.cliPath' doesn't exist: ${configured}` };
  }
  const entry = settings.compilerEntry ?? undefined;
  if (entry) {
    const built = path.join(path.dirname(entry), "build", "myla");
    if (exists(built)) return asCommand(built);
    if (exists(entry)) return asCommand(entry);
  }
  return {
    missing:
      "The myla CLI wasn't found: open the Myla repository (build it with scripts/bootstrap.sh), or set 'myla.cliPath' or 'myla.compilerPath'.",
  };
}

export type MylaCommand = "run" | "test" | "build";

/**
 * The arguments of `myla <command> <file> [extra]`. A build without `-o`
 * writes the binary next to the source, without the extension, like
 * `cc x.c -o x`; `file` may be `${file}`, which VS Code substitutes in tasks.
 */
export function cliCommandArgs(cli: Toolchain, command: MylaCommand, file: string, extra: string[]): string[] {
  if (command === "build" && !extra.includes("-o")) {
    const out =
      file === "${file}" ? "${fileDirname}/${fileBasenameNoExtension}" : file.endsWith(".my") ? file.slice(0, -3) : `${file}.out`;
    return [...cli.args, "build", file, "-o", out, ...extra];
  }
  return [...cli.args, command, file, ...extra];
}
