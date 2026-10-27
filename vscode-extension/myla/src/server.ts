import * as path from "path";

/** What the extension knows when it starts a language server. */
export interface ServerSettings {
  /** `myla.server`: "myla" (the default) or "python". */
  server: string;
  /** `myla.serverPath`, expanded: the Myla server's binary, or "". */
  serverPath: string;
  /** The repository's `myla.py`, when found. */
  compilerEntry: string | null | undefined;
  /** The Python interpreter for the Python server. */
  python: string;
}

/** The server to start: a command line, and what to tell the user. */
export interface ServerChoice {
  kind: "myla" | "python";
  command: string;
  args: string[];
  cwd?: string;
  /** Whether to send `workspace/didChangeWatchedFiles` for `**\/*.my`. */
  watchFiles: boolean;
  /** Why the preferred server isn't used, if it isn't. */
  note?: string;
}

/**
 * The language server to start (MYLA-80): the one written in Myla when its
 * binary exists (`myla.serverPath`, else `build/myla-lsp` in the repository,
 * as `scripts/bootstrap.sh` builds it), else the Python one (`myla.py lsp`).
 * Undefined when neither can be found. `exists` tells whether a path exists.
 */
export function chooseServer(
  settings: ServerSettings,
  exists: (p: string) => boolean
): ServerChoice | undefined {
  const entry = settings.compilerEntry ?? undefined;
  const repoRoot = entry ? path.dirname(entry) : undefined;
  let note: string | undefined;
  if (settings.server !== "python") {
    const binary =
      settings.serverPath ||
      (repoRoot ? path.join(repoRoot, "build", "myla-lsp") : "");
    if (binary && exists(binary)) {
      // the binary finds the standard library next to its build/ directory;
      // name the repository's when it is known
      const stdlib = repoRoot ? path.join(repoRoot, "src", "myla") : "";
      const args =
        stdlib && exists(path.join(stdlib, "std")) ? ["--stdlib", stdlib] : [];
      return { kind: "myla", command: binary, args, cwd: repoRoot, watchFiles: true };
    }
    note = binary
      ? `The Myla language server isn't built (${binary}): build it with scripts/bootstrap.sh. Using the Python server.`
      : "The Myla language server wasn't found: set 'myla.serverPath' or 'myla.compilerPath'. Using the Python server.";
  }
  if (!entry) {
    return undefined;
  }
  return {
    kind: "python",
    command: settings.python,
    args: [entry, "lsp"],
    cwd: repoRoot,
    watchFiles: false,
    note,
  };
}
