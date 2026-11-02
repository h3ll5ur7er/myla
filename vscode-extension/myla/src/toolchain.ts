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

/** The file that marks the repository's root: the CLI's source. */
export const ROOT_MARKER = path.join("selfhost", "main.my");

/** The repository's root, from the marker `findCompilerEntry` found. */
export function repoRootOf(entry: string): string {
  return path.dirname(path.dirname(entry));
}

/**
 * The repository's marker file `selfhost/main.my` (MYLA-219: `myla.py` marked
 * it until the Python toolchain was retired): `myla.compilerPath` (the root,
 * or a file directly in it, such as an old `myla.py` setting), else the first
 * workspace folder that has one.
 */
export function findCompilerEntry(
  configured: string,
  workspaceFolders: string[],
  exists: (p: string) => boolean,
): string | undefined {
  if (configured) {
    const root = /\.[a-z]+$/.test(configured) ? path.dirname(configured) : configured;
    const candidate = path.join(root, ROOT_MARKER);
    return exists(candidate) ? candidate : undefined;
  }
  for (const folder of workspaceFolders) {
    const candidate = path.join(folder, ROOT_MARKER);
    if (exists(candidate)) return candidate;
  }
  return undefined;
}

/**
 * The `myla` CLI for run, test, build and debug builds: `myla.cliPath`, else
 * the self-hosted `build/myla` of the repository (built by
 * `scripts/bootstrap.sh`).
 */
export function chooseCli(
  settings: { cliPath: string; compilerEntry: string | null | undefined },
  exists: (p: string) => boolean,
): Toolchain | ToolMissing {
  const configured = settings.cliPath;
  if (configured) {
    // a bare name such as `myla` is looked up on PATH when it runs
    if (!configured.includes("/") || exists(configured)) return { command: configured, args: [] };
    return { missing: `The myla CLI set in 'myla.cliPath' doesn't exist: ${configured}` };
  }
  const entry = settings.compilerEntry ?? undefined;
  if (entry) {
    const built = path.join(repoRootOf(entry), "build", "myla");
    if (exists(built)) return { command: built, args: [] };
  }
  return {
    missing:
      "The myla CLI wasn't found: open the Myla repository and build it with scripts/bootstrap.sh, or set 'myla.cliPath'.",
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
