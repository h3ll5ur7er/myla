"""Adapter around the Myla front end for tooling.

`check_file` runs the exact same pipeline the CLI's `check` command uses —
``link`` (module resolution) then ``types.check`` — but against an in-memory
buffer, and returns structured diagnostics instead of a rendered string. It
never prints and never propagates an exception: a compiler crash becomes a
single "internal error" diagnostic so the language server stays alive.

The compiler uses panic-mode error handling (the first error in a stage aborts
it), so today this yields at most one diagnostic per file. The list-returning
shape is kept so batch diagnostics can drop in later without an API change.
"""
from __future__ import annotations

import os

from ..errors import MylaError
from ..loader import default_stdlib_root, link
from ..types import check
from .diagnostics import CompilerDiagnostic, DiagnosticSeverity, SourceRange
from .positions import identifier_end_column, to_lsp_position
from .symbols import Symbol, document_symbols

# Compiler error `kind` labels (e.g. "type error") -> LSP diagnostic code.
_KIND_CODE = {
    "lex error": "lex",
    "parse error": "parse",
    "type error": "type",
    "module error": "module",
    "runtime error": "runtime",
}


def _diagnostic_from_myla_error(
    err: MylaError, source_lines: list[str], path: str
) -> CompilerDiagnostic:
    code = _KIND_CODE.get(err.kind, err.kind.split()[0] if err.kind else None)

    if err.line is None:
        # No position: attach at the top of the file so it is still visible.
        rng = SourceRange(0, 0, 0, 1)
    else:
        col = err.column if err.column is not None else 1
        start_line, start_char = to_lsp_position(source_lines, err.line, col)
        line_text = (
            source_lines[start_line] if start_line < len(source_lines) else ""
        )
        end_col = identifier_end_column(line_text, col)
        _, end_char = to_lsp_position(source_lines, err.line, end_col)
        rng = SourceRange(start_line, start_char, start_line, end_char)

    return CompilerDiagnostic(
        range=rng,
        message=err.message,
        severity=DiagnosticSeverity.ERROR,
        code=code,
        source="myla",
        path=path,
    )


def check_file(
    path: str, source: str | None = None, open_sources: dict[str, str] | None = None
) -> list[CompilerDiagnostic]:
    """Type-check `path` (using `source` as its in-memory contents when given,
    and `open_sources` for other modules open in the editor) and return the
    resulting diagnostics, each with the path of the file it is in: an error in
    an imported module belongs to that module (MYLA-10).

    Returns an empty list when the program checks cleanly."""
    overrides = {os.path.realpath(p): text for p, text in (open_sources or {}).items()}
    if source is not None:
        overrides[os.path.realpath(path)] = source

    try:
        program = link(
            path,
            stdlib_root=default_stdlib_root(),
            source_overrides=overrides,
        )
        check(program)
        return []
    except MylaError as err:
        err_path = os.path.realpath(err.path or path)
        text = overrides.get(err_path)
        if text is None:
            try:
                with open(err_path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                text = ""
        return [_diagnostic_from_myla_error(err, text.splitlines(), err_path)]
    except Exception as exc:  # noqa: BLE001 - never crash the server on bad input
        return [
            CompilerDiagnostic(
                range=SourceRange(0, 0, 0, 1),
                message=(
                    f"internal Myla language server error while checking "
                    f"{os.path.basename(path)}: {exc}"
                ),
                severity=DiagnosticSeverity.ERROR,
                code="internal-error",
                source="myla",
            )
        ]


def diagnostics_by_file(
    path: str, diagnostics: list[CompilerDiagnostic]
) -> dict[str, list[CompilerDiagnostic]]:
    """Group `diagnostics` from checking `path` by the file they are in. The
    checked file is always present, so publishing the groups also clears its
    old diagnostics."""
    checked = os.path.realpath(path)
    groups: dict[str, list[CompilerDiagnostic]] = {checked: []}
    for d in diagnostics:
        groups.setdefault(d.path or checked, []).append(d)
    return groups


def parse_symbols(path: str, source: str) -> list[Symbol]:
    """Return the outline (document symbols) for `source`.

    Delegates to `symbols.document_symbols`; kept here so the server has a single
    compiler-facing module. `path` is currently unused (symbols come from the
    in-memory buffer) but is accepted for API symmetry with `check_file`."""
    try:
        return document_symbols(path, source)
    except Exception:  # noqa: BLE001 - an outline failure must not crash anything
        return []


def definition_at(
    path: str, source: str, line: int, character: int
) -> SourceRange | None:
    """Return the declaration range for the identifier at the 0-based
    (`line`, `character`) position, or None. Delegates to `definition`."""
    try:
        return _definition_at(path, source, line, character)
    except Exception:  # noqa: BLE001 - a lookup failure must not crash anything
        return None
