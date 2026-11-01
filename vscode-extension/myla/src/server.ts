import * as path from "path";
import { repoRootOf } from "./toolchain.ts";

/** What the extension knows when it starts the language server. */
export interface ServerSettings {
  /** `myla.serverPath`, expanded: the server's binary, or "". */
  serverPath: string;
  /** The repository's marker `selfhost/main.my`, when found (`findCompilerEntry`). */
  compilerEntry: string | null | undefined;
}

/** The server's command line. */
export interface ServerChoice {
  command: string;
  args: string[];
  cwd?: string;
}

/** Why there is no server to start. */
export interface ServerMissing {
  missing: string;
}

/**
 * The language server written in Myla (MYLA-80): `myla.serverPath`, else
 * `build/myla-lsp` in the repository, as `scripts/bootstrap.sh` builds it.
 * The Python server it replaced is gone (MYLA-83). `exists` tells whether a
 * path exists.
 */
export function chooseServer(
  settings: ServerSettings,
  exists: (p: string) => boolean
): ServerChoice | ServerMissing {
  const entry = settings.compilerEntry ?? undefined;
  const repoRoot = entry ? repoRootOf(entry) : undefined;
  const binary =
    settings.serverPath ||
    (repoRoot ? path.join(repoRoot, "build", "myla-lsp") : "");
  if (!binary) {
    return {
      missing:
        "The Myla language server wasn't found: set 'myla.serverPath' to a built myla-lsp, or 'myla.compilerPath' to the repository.",
    };
  }
  if (!exists(binary)) {
    return {
      missing: `The Myla language server isn't built (${binary}): build it with scripts/bootstrap.sh, or set 'myla.serverPath'.`,
    };
  }
  // the binary finds the standard library next to its build/ directory;
  // name the repository's when it is known
  const stdlib = repoRoot ? path.join(repoRoot, "src", "myla") : "";
  const args =
    stdlib && exists(path.join(stdlib, "std")) ? ["--stdlib", stdlib] : [];
  return { command: binary, args, cwd: repoRoot };
}
