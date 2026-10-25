"""The Myla language server (pygls, stdio).

Phase 1 scope: publish compiler diagnostics for `.my` documents on open, change
(debounced), and save. Everything routes through `compiler_adapter.check_file`,
so the compiler remains the single source of truth. Later phases (symbols,
definition, hover, ...) register additional features on the same `server`.

Run via `myla lsp` (see myla.cli) or `python -m myla.lsp`.
"""
from __future__ import annotations

import logging
import os
import threading

from lsprotocol import types as lsp
from pygls.lsp.server import LanguageServer
from pygls.uris import from_fs_path, to_fs_path

from . import compiler_adapter
from .completion import Completion, completions
from .definition import definition_at
from .diagnostics import CompilerDiagnostic, DiagnosticSeverity, Location
from .hover import hover_at
from .references import references_at
from .symbols import Symbol, SymbolKind
from .workspace import WorkspaceIndex

logger = logging.getLogger("myla.lsp")

# Wait this long after the last keystroke before re-checking a changed document,
# so we don't run the whole front end on every character (see LSP_DESCRIPTION.md
# "Phase 2 performance requirements").
_DEBOUNCE_SECONDS = 0.4

_SEVERITY = {
    DiagnosticSeverity.ERROR: lsp.DiagnosticSeverity.Error,
    DiagnosticSeverity.WARNING: lsp.DiagnosticSeverity.Warning,
    DiagnosticSeverity.INFO: lsp.DiagnosticSeverity.Information,
    DiagnosticSeverity.HINT: lsp.DiagnosticSeverity.Hint,
}

_SYMBOL_KIND = {
    SymbolKind.STRUCT: lsp.SymbolKind.Struct,
    SymbolKind.FUNCTION: lsp.SymbolKind.Function,
    SymbolKind.METHOD: lsp.SymbolKind.Method,
    SymbolKind.ENUM: lsp.SymbolKind.Enum,
    SymbolKind.ENUM_MEMBER: lsp.SymbolKind.EnumMember,
    SymbolKind.INTERFACE: lsp.SymbolKind.Interface,
    SymbolKind.IMPL: lsp.SymbolKind.Object,
    SymbolKind.FIELD: lsp.SymbolKind.Field,
    SymbolKind.CONSTANT: lsp.SymbolKind.Constant,
    SymbolKind.TYPE_ALIAS: lsp.SymbolKind.Class,
}

_COMPLETION_KIND = {
    "keyword": lsp.CompletionItemKind.Keyword,
    "function": lsp.CompletionItemKind.Function,
    "method": lsp.CompletionItemKind.Method,
    "struct": lsp.CompletionItemKind.Struct,
    "enum": lsp.CompletionItemKind.Enum,
    "enum_member": lsp.CompletionItemKind.EnumMember,
    "interface": lsp.CompletionItemKind.Interface,
    "field": lsp.CompletionItemKind.Field,
    "constant": lsp.CompletionItemKind.Constant,
    "type_alias": lsp.CompletionItemKind.Class,
}


class MylaLanguageServer(LanguageServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # uri -> pending debounce timer for change events.
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._debounce_lock = threading.Lock()
        # Cross-file symbol index and the set of currently-open document URIs.
        self.index = WorkspaceIndex()
        self._open_uris: set[str] = set()
        self._roots_ready = False
        # checked uri -> other files it last published diagnostics for (an
        # error in an imported module is shown in that module, MYLA-10)
        self._published_elsewhere: dict[str, set[str]] = {}

    def ensure_roots(self) -> None:
        """Populate the workspace index roots from the client's workspace
        folders on first use (the workspace isn't available until after
        initialize, so this is done lazily rather than in __init__)."""
        if self._roots_ready:
            return
        roots: list[str] = []
        try:
            folders = getattr(self.workspace, "folders", None) or {}
            for folder in folders.values():
                path = to_fs_path(folder.uri)
                if path:
                    roots.append(path)
            if not roots:
                root_uri = getattr(self.workspace, "root_uri", None)
                if root_uri:
                    path = to_fs_path(root_uri)
                    if path:
                        roots.append(path)
        except Exception:  # noqa: BLE001 - workspace not ready yet
            return
        self.index.set_roots(roots)
        self._roots_ready = True

    def overrides(self) -> dict[str, str]:
        """Current text of every open document, keyed by file path — so the
        workspace index reflects unsaved edits."""
        result: dict[str, str] = {}
        for uri in self._open_uris:
            path = to_fs_path(uri)
            if path is None:
                continue
            try:
                result[path] = self.workspace.get_text_document(uri).source
            except Exception:  # noqa: BLE001 - closed/untracked
                continue
        return result

    def schedule_check(self, uri: str, delay: float) -> None:
        """(Re)schedule a diagnostics run for `uri`, cancelling any pending one."""
        with self._debounce_lock:
            existing = self._debounce_timers.pop(uri, None)
            if existing is not None:
                existing.cancel()
            if delay > 0:
                timer = threading.Timer(delay, self._run_check, args=(uri,))
                timer.daemon = True
                self._debounce_timers[uri] = timer
                timer.start()
        # Run the immediate case *outside* the lock: `_run_check` re-acquires
        # `_debounce_lock`, which is not reentrant, so calling it while holding
        # the lock would deadlock.
        if delay <= 0:
            self._run_check(uri)

    def _run_check(self, uri: str) -> None:
        with self._debounce_lock:
            self._debounce_timers.pop(uri, None)
        try:
            self.publish_for(uri)
        except Exception:  # noqa: BLE001 - a bad check must not kill the server
            logger.exception("failed to publish diagnostics for %s", uri)

    def publish_for(self, uri: str) -> None:
        path = to_fs_path(uri)
        if path is None:
            return
        try:
            document = self.workspace.get_text_document(uri)
            source = document.source
        except Exception:  # noqa: BLE001 - untracked/closed document
            source = None

        diagnostics = compiler_adapter.check_file(path, source, self.overrides())
        by_uri: dict[str, list[CompilerDiagnostic]] = {}
        for file, group in compiler_adapter.diagnostics_by_file(path, diagnostics).items():
            same = os.path.realpath(file) == os.path.realpath(path)
            by_uri[uri if same else (from_fs_path(file) or "file://" + file)] = group
        # clear files this document's errors were shown in last time
        for stale in self._published_elsewhere.get(uri, set()) - by_uri.keys():
            by_uri[stale] = []
        self._published_elsewhere[uri] = {u for u, g in by_uri.items() if u != uri and g}
        for target, group in by_uri.items():
            self.text_document_publish_diagnostics(
                lsp.PublishDiagnosticsParams(
                    uri=target,
                    diagnostics=[_to_lsp_diagnostic(d) for d in group],
                )
            )


def _to_lsp_diagnostic(d: CompilerDiagnostic) -> lsp.Diagnostic:
    return lsp.Diagnostic(
        range=lsp.Range(
            start=lsp.Position(line=d.range.start_line, character=d.range.start_col),
            end=lsp.Position(line=d.range.end_line, character=d.range.end_col),
        ),
        message=d.message,
        severity=_SEVERITY.get(d.severity, lsp.DiagnosticSeverity.Error),
        source=d.source,
        code=d.code,
    )


def _range(r) -> lsp.Range:
    return lsp.Range(
        start=lsp.Position(line=r.start_line, character=r.start_col),
        end=lsp.Position(line=r.end_line, character=r.end_col),
    )


def _to_lsp_symbol(sym: Symbol) -> lsp.DocumentSymbol:
    return lsp.DocumentSymbol(
        name=sym.name,
        detail=sym.detail or None,
        kind=_SYMBOL_KIND.get(sym.kind, lsp.SymbolKind.Object),
        range=_range(sym.range),
        selection_range=_range(sym.selection_range),
        children=[_to_lsp_symbol(c) for c in sym.children],
    )


def _to_lsp_location(loc: Location) -> lsp.Location:
    uri = from_fs_path(loc.path) or ("file://" + loc.path)
    return lsp.Location(uri=uri, range=_range(loc.range))


server = MylaLanguageServer("myla-lsp", "0.1.0")


@server.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: MylaLanguageServer, params: lsp.DidOpenTextDocumentParams) -> None:
    logger.debug("did_open fired for %s", params.text_document.uri)
    ls._open_uris.add(params.text_document.uri)
    ls.schedule_check(params.text_document.uri, delay=0)


@server.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: MylaLanguageServer, params: lsp.DidChangeTextDocumentParams) -> None:
    ls.schedule_check(params.text_document.uri, delay=_DEBOUNCE_SECONDS)


@server.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: MylaLanguageServer, params: lsp.DidSaveTextDocumentParams) -> None:
    ls.schedule_check(params.text_document.uri, delay=0)


@server.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(ls: MylaLanguageServer, params: lsp.DidCloseTextDocumentParams) -> None:
    ls._open_uris.discard(params.text_document.uri)
    # Clear diagnostics for a closed document so stale squiggles don't linger.
    ls.text_document_publish_diagnostics(
        lsp.PublishDiagnosticsParams(uri=params.text_document.uri, diagnostics=[])
    )


def _document(ls: MylaLanguageServer, uri: str) -> tuple[str, str] | None:
    """Resolve (path, source) for a request, or None if unavailable."""
    path = to_fs_path(uri)
    if path is None:
        return None
    try:
        return path, ls.workspace.get_text_document(uri).source
    except Exception:  # noqa: BLE001 - untracked/closed document
        return None


@server.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(
    ls: MylaLanguageServer, params: lsp.DocumentSymbolParams
) -> list[lsp.DocumentSymbol]:
    doc = _document(ls, params.text_document.uri)
    if doc is None:
        return []
    path, source = doc
    symbols = compiler_adapter.parse_symbols(path, source)
    return [_to_lsp_symbol(s) for s in symbols]


@server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
def definition(
    ls: MylaLanguageServer, params: lsp.DefinitionParams
) -> lsp.Location | None:
    doc = _document(ls, params.text_document.uri)
    if doc is None:
        return None
    path, source = doc
    ls.ensure_roots()
    overrides = ls.overrides()
    target = definition_at(
        path, source, params.position.line, params.position.character,
        resolver=lambda name: ls.index.lookup(name, overrides),
    )
    return _to_lsp_location(target) if target is not None else None


@server.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(ls: MylaLanguageServer, params: lsp.HoverParams) -> lsp.Hover | None:
    doc = _document(ls, params.text_document.uri)
    if doc is None:
        return None
    path, source = doc
    ls.ensure_roots()
    overrides = ls.overrides()
    markdown = hover_at(
        path, source, params.position.line, params.position.character,
        resolver=lambda name: ls.index.best_symbol(name, overrides),
    )
    if markdown is None:
        return None
    return lsp.Hover(
        contents=lsp.MarkupContent(kind=lsp.MarkupKind.Markdown, value=markdown)
    )


@server.feature(lsp.TEXT_DOCUMENT_REFERENCES)
def references(
    ls: MylaLanguageServer, params: lsp.ReferenceParams
) -> list[lsp.Location]:
    doc = _document(ls, params.text_document.uri)
    if doc is None:
        return []
    path, source = doc
    ls.ensure_roots()
    overrides = ls.overrides()
    include_decl = params.context.include_declaration if params.context else True
    locations = references_at(
        path, source, params.position.line, params.position.character,
        include_declaration=include_decl,
        resolver=lambda name: ls.index.references(name, overrides),
    )
    return [_to_lsp_location(loc) for loc in locations]


@server.feature(lsp.TEXT_DOCUMENT_COMPLETION)
def completion(
    ls: MylaLanguageServer, params: lsp.CompletionParams
) -> lsp.CompletionList:
    doc = _document(ls, params.text_document.uri)
    if doc is None:
        return lsp.CompletionList(is_incomplete=False, items=[])
    path, source = doc
    ls.ensure_roots()
    overrides = ls.overrides()
    workspace_symbols = ls.index.completion_symbols(overrides)
    items = completions(
        path, source, params.position.line, params.position.character,
        workspace_symbols=workspace_symbols,
    )
    return lsp.CompletionList(
        is_incomplete=False,
        items=[
            lsp.CompletionItem(
                label=c.label,
                kind=_COMPLETION_KIND.get(c.kind, lsp.CompletionItemKind.Text),
                detail=c.detail or None,
            )
            for c in items
        ],
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    server.start_io()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

