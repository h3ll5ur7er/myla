"""Myla language server.

A thin Language Server Protocol wrapper around the Myla bootstrapping compiler
(the same front end the CLI uses). The compiler is the single source of truth
for diagnostics, symbols, and — eventually — hover/definition/etc.; nothing here
re-implements lexing, parsing, or type checking.

Layout (see vscode-extension/myla/LSP_DESCRIPTION.md):
    positions.py        1-based compiler positions -> 0-based LSP positions
    diagnostics.py      compiler-independent diagnostic model
    compiler_adapter.py invoke the front end, convert errors to diagnostics
    server.py           the pygls stdio server

The server is launched via `myla lsp` (see myla.cli).
"""
from __future__ import annotations

__all__ = ["main"]


def main() -> int:
    """Entry point used by the `myla lsp` CLI subcommand."""
    from .server import main as _main

    return _main()
