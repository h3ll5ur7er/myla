Below is a detailed implementation brief you can pass to an AI agent or human developer with access to your Myla codebase.

---

# Myla VS Code Language Integration Brief

## Goal

Integrate the existing **Python bootstrapping compiler** into the Myla VS Code extension to provide real language intelligence.

The extension already has:

```text
.my file recognition
TextMate syntax highlighting
language-configuration.json
snippets
basic TypeScript extension scaffold
placeholder commands
```

The next goal is to add real editor features by using the Python compiler as the source of truth.

Priority order:

```text
1. Diagnostics
2. Document symbols / outline
3. Go to definition
4. Hover
5. Completion
6. Formatting
7. Semantic tokens
8. Rename / references
```

Start with **diagnostics**, because the Python compiler already produces good errors.

---

# Current language facts

The language is called **Myla**. The Tree-sitter grammar uses:

```js
name: 'myla'
```

and the source file rule is a sequence of top-level items such as functions, structs, enums, traits, impls, actors, type aliases, constants, and imports. 

The current grammar includes top-level constructs like:

```myla
fun
struct
enum
trait
impl
actor
typealias
const
import
from ... import ...
```

It also includes expressions such as:

```myla
if
match
lambda
spawn
go
await
field access
indexing
calls
binary operators
pipeline operator |>
```

and comments:

```myla
// line comment
/* block comment */
```

The existing VS Code extension should continue using TextMate for basic syntax highlighting. The Python compiler integration should provide semantic/editor intelligence.

---

# Recommended architecture

Use a **Language Server Protocol server** written in Python, and have the VS Code extension start it.

Recommended structure:

```text
myla-vscode/
  package.json
  language-configuration.json
  syntaxes/
    myla.tmLanguage.json
  snippets/
    myla.code-snippets
  src/
    extension.ts

myla-language-server/
  pyproject.toml
  myla_lsp/
    __init__.py
    server.py
    compiler_adapter.py
    diagnostics.py
    symbols.py
    positions.py
```

Depending on your repository layout, the language server can live either:

```text
tools/myla-language-server/
```

or:

```text
crates/editor/myla-language-server/
```

or:

```text
editors/vscode/server/
```

The important thing is that the VS Code extension can run it as a subprocess.

---

# Design principle

Do **not** reimplement parsing/type-checking in TypeScript.

The Python compiler should be the source of truth for:

```text
syntax errors
type errors
name resolution
symbol locations
hover information
formatting, if available
```

The VS Code extension should only:

```text
start the language server
send document changes
receive diagnostics
display language features
```

---

# Phase 1: define a compiler adapter API

Before implementing full LSP features, create a small Python adapter around the existing compiler.

The adapter should expose these operations:

```python
check_file(path: str, source: str | None = None) -> list[Diagnostic]
parse_symbols(path: str, source: str | None = None) -> list[Symbol]
definition_at(path: str, source: str, line: int, character: int) -> Location | None
hover_at(path: str, source: str, line: int, character: int) -> Hover | None
format_file(path: str, source: str) -> str | None
```

The initial implementation can support only:

```python
check_file(...)
```

Everything else can return `None` or `[]` until implemented.

---

# Phase 1 diagnostic model

Create an internal diagnostic model independent of LSP:

```python
from dataclasses import dataclass
from enum import Enum


class DiagnosticSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


@dataclass
class SourceRange:
    file: str
    start_line: int      # 0-based
    start_col: int       # 0-based UTF-16 column preferred for LSP
    end_line: int
    end_col: int


@dataclass
class CompilerDiagnostic:
    range: SourceRange
    message: str
    severity: DiagnosticSeverity
    code: str | None = None
    source: str = "myla"
```

Important: LSP positions are **zero-based** and use **UTF-16 code units** for character offsets. If the compiler reports one-based line/column numbers, normalize them in one place.

Create helpers:

```python
def compiler_position_to_lsp(line: int, col: int) -> tuple[int, int]:
    ...
```

and use them everywhere.

---

# Phase 1 compiler adapter

Create a file like:

```text
myla_lsp/compiler_adapter.py
```

Purpose:

```text
Take a file path or in-memory source string.
Invoke the existing Python compiler's parser/checker.
Convert compiler errors into CompilerDiagnostic objects.
Never print directly to stdout.
Never crash the LSP process on compiler errors.
```

Pseudo-code:

```python
from .diagnostics import CompilerDiagnostic, SourceRange, DiagnosticSeverity


def check_file(path: str, source: str | None = None) -> list[CompilerDiagnostic]:
    try:
        # Preferred:
        # call compiler API directly if one exists.
        #
        # Example shape:
        # ast = myla.parse(source, filename=path)
        # result = myla.typecheck(ast)
        # return convert_errors(result.errors)

        ...
    except MylaCompilerError as exc:
        return [convert_compiler_error(exc)]
    except Exception as exc:
        return [
            CompilerDiagnostic(
                range=SourceRange(
                    file=path,
                    start_line=0,
                    start_col=0,
                    end_line=0,
                    end_col=1,
                ),
                message=f"Internal Myla language server error: {exc}",
                severity=DiagnosticSeverity.ERROR,
                code="internal-error",
            )
        ]
```

If the compiler currently only exposes a CLI, create a temporary CLI adapter:

```python
subprocess.run(
    ["python", "-m", "myla", "check", path, "--json"],
    capture_output=True,
    text=True,
)
```

But the best long-term path is to call compiler functions directly.

---

# Required compiler-side improvement

If the compiler does not already have a machine-readable output mode, add one.

Add a command like:

```bash
myla check --json path/to/file.my
```

Expected JSON shape:

```json
{
  "ok": false,
  "diagnostics": [
    {
      "severity": "error",
      "message": "unknown variable `foo`",
      "file": "/absolute/path/example.my",
      "start_line": 12,
      "start_col": 8,
      "end_line": 12,
      "end_col": 11,
      "code": "E_UNKNOWN_NAME"
    }
  ]
}
```

Line/column can be one-based or zero-based internally, but document it clearly and normalize it in the LSP adapter.

Do **not** parse pretty human-readable error messages if avoidable. Keep the beautiful human output for the terminal, but expose structured diagnostics for tools.

---

# Phase 2: implement the Python LSP server

Use Python. Recommended packages:

```text
pygls
lsprotocol
```

The server should communicate over stdio.

Create:

```text
myla_lsp/server.py
```

Minimal server responsibilities:

```text
on initialize
on textDocument/didOpen
on textDocument/didChange
on textDocument/didSave
run compiler diagnostics
publish textDocument/publishDiagnostics
```

Pseudo-code:

```python
from pygls.server import LanguageServer
from lsprotocol.types import (
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_SAVE,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    DidSaveTextDocumentParams,
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
)

from .compiler_adapter import check_file


class MylaLanguageServer(LanguageServer):
    pass


server = MylaLanguageServer("myla-lsp", "0.1.0")


documents: dict[str, str] = {}


def uri_to_path(uri: str) -> str:
    ...


def publish_diagnostics_for_uri(uri: str):
    path = uri_to_path(uri)
    source = documents.get(uri)

    compiler_diagnostics = check_file(path, source)

    lsp_diagnostics = []
    for d in compiler_diagnostics:
        lsp_diagnostics.append(
            Diagnostic(
                range=Range(
                    start=Position(
                        line=d.range.start_line,
                        character=d.range.start_col,
                    ),
                    end=Position(
                        line=d.range.end_line,
                        character=d.range.end_col,
                    ),
                ),
                message=d.message,
                severity=to_lsp_severity(d.severity),
                source=d.source,
                code=d.code,
            )
        )

    server.publish_diagnostics(uri, lsp_diagnostics)


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: MylaLanguageServer, params: DidOpenTextDocumentParams):
    documents[params.text_document.uri] = params.text_document.text
    publish_diagnostics_for_uri(params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: MylaLanguageServer, params: DidChangeTextDocumentParams):
    # For first implementation, use full-document sync.
    documents[params.text_document.uri] = params.content_changes[-1].text
    publish_diagnostics_for_uri(params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: MylaLanguageServer, params: DidSaveTextDocumentParams):
    publish_diagnostics_for_uri(params.text_document.uri)


def main():
    server.start_io()


if __name__ == "__main__":
    main()
```

Use **full document sync** first. Incremental sync can come later.

---

# Phase 2 performance requirements

Diagnostics should be debounced.

Do not run the compiler on every keystroke immediately.

Recommended behavior:

```text
didOpen: run immediately
didSave: run immediately
didChange: wait 300–500ms after last edit
```

For the first implementation, debouncing can happen either:

```text
inside the Python LSP server
```

or:

```text
inside the VS Code client
```

Prefer server-side debouncing if possible, because it also helps other future editors.

---

# Phase 3: wire VS Code extension to the language server

Update the VS Code extension to use:

```text
vscode-languageclient
```

Install dependencies:

```bash
npm install vscode-languageclient
```

Update `src/extension.ts`.

Target behavior:

```text
When a .my / myla document is opened, start the Python language server.
Use stdio transport.
Pass workspace root to the server.
Allow configuring the Python executable and server path.
```

Example TypeScript shape:

```ts
import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration("myla");

  const pythonPath = config.get<string>("pythonPath") || "python";

  const serverModule = context.asAbsolutePath(
    path.join("server", "myla_lsp", "server.py")
  );

  const serverOptions: ServerOptions = {
    command: pythonPath,
    args: [serverModule],
    transport: TransportKind.stdio
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "myla" },
      { scheme: "untitled", language: "myla" }
    ],
    synchronize: {
      fileEvents: vscode.workspace.createFileSystemWatcher("**/*.my")
    }
  };

  client = new LanguageClient(
    "mylaLanguageServer",
    "Myla Language Server",
    serverOptions,
    clientOptions
  );

  context.subscriptions.push(client.start());

  context.subscriptions.push(
    vscode.commands.registerCommand("myla.showExtensionInfo", () => {
      vscode.window.showInformationMessage("Myla extension is active.");
    })
  );
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
```

---

# VS Code settings to add

In `package.json`, add configuration options:

```json
{
  "contributes": {
    "configuration": {
      "title": "Myla",
      "properties": {
        "myla.pythonPath": {
          "type": "string",
          "default": "python",
          "description": "Path to the Python executable used to run the Myla language server."
        },
        "myla.compilerPath": {
          "type": "string",
          "default": "",
          "description": "Path to the Myla compiler entrypoint or repository root. Leave empty to auto-detect."
        },
        "myla.diagnostics.enable": {
          "type": "boolean",
          "default": true,
          "description": "Enable Myla compiler diagnostics."
        },
        "myla.diagnostics.run": {
          "type": "string",
          "enum": ["onType", "onSave"],
          "default": "onType",
          "description": "When to run Myla diagnostics."
        }
      }
    }
  }
}
```

The language server should read initialization options from the client later.

---

# Phase 4: package the Python server with the extension

There are two possible approaches.

## Option A: extension includes the server

Put the Python LSP server inside the VS Code extension:

```text
myla-vscode/
  server/
    myla_lsp/
      server.py
      compiler_adapter.py
```

This is easiest while developing.

Problem: the server still needs access to the compiler package.

Possible solutions:

```text
1. Use myla.compilerPath to point at the source checkout.
2. Vendor/import the compiler package if licensing/repo layout allows it.
3. Use the installed myla Python package if available.
```

## Option B: server is installed separately

The VS Code extension runs:

```bash
myla-lsp
```

or:

```bash
python -m myla_lsp
```

This is cleaner long-term.

The extension setting becomes:

```json
"myla.languageServerPath": {
  "type": "string",
  "default": "myla-lsp"
}
```

For now, Option A is probably smoother.

---

# Phase 5: diagnostics implementation details

Diagnostics should work for:

```text
syntax errors
type errors
unknown names
wrong arity
trait/impl errors
import errors
unreachable paths if compiler supports them
```

When the compiler reports a diagnostic, preserve:

```text
main message
source range
severity
error code
notes, if available
related spans, if available
```

LSP supports related information. If the compiler has notes like:

```text
defined here
previously declared here
expected type came from here
```

map them to `DiagnosticRelatedInformation`.

Example:

```python
DiagnosticRelatedInformation(
    location=Location(
        uri=path_to_uri(note.file),
        range=Range(...)
    ),
    message=note.message
)
```

---

# Phase 6: document symbols / outline

After diagnostics, implement document symbols.

The compiler or parser should return symbols like:

```text
function
struct
enum
enum variant
trait
impl
actor
field
const
typealias
method
```

Use LSP `textDocument/documentSymbol`.

Expected Myla mapping:

```text
fun name(...)        -> SymbolKind.Function
struct Name         -> SymbolKind.Struct
enum Name           -> SymbolKind.Enum
variant             -> SymbolKind.EnumMember
trait Name          -> SymbolKind.Interface
impl Type           -> SymbolKind.Object or Namespace
actor Name          -> SymbolKind.Class
field: Type         -> SymbolKind.Field
const NAME          -> SymbolKind.Constant
typealias Name      -> SymbolKind.TypeParameter or Class
```

If nested symbols are easy, return hierarchical symbols:

```text
struct User
  name
  age

trait Display
  to_string

impl User
  to_string
```

If not, return a flat list first.

---

# Phase 7: Go to Definition

Ctrl+click requires `textDocument/definition`.

Implementation requirements:

```text
Given file, source, line, character:
1. Find token at position.
2. Ask compiler name resolver for symbol under cursor.
3. Return declaration location.
```

Do not implement this with regex except as a temporary prototype.

The compiler should expose something like:

```python
def definition_at(path: str, source: str, line: int, character: int) -> Location | None:
    ...
```

It should support at least:

```text
local variable -> let/var/parameter declaration
function call -> function declaration
type name -> struct/enum/trait/typealias declaration
field access -> field declaration if known
method call -> impl/trait method declaration if known
imported name -> imported declaration if available
const name -> const declaration
```

Start with top-level symbols only if full name resolution is not ready.

Minimal first pass:

```text
Index all top-level symbols in workspace.
If cursor is on an identifier, jump to matching top-level declaration.
```

Better second pass:

```text
Use compiler symbol table / resolver.
```

---

# Phase 8: Hover

Implement `textDocument/hover`.

Suggested hover content:

```text
function signature
type of expression
struct fields
enum variants
trait method signature
const type/value if cheap
documentation comment if available
```

Example hover:

````markdown
```myla
fun add(a: Int, b: Int) -> Int
````

````

For variables:

```markdown
```myla
let result: Int
````

````

Compiler API shape:

```python
def hover_at(path: str, source: str, line: int, character: int) -> str | None:
    ...
````

Return Markdown.

---

# Phase 9: Completion

Implement `textDocument/completion`.

Start simple:

```text
keywords
snippets already exist in VS Code
top-level symbols
locals in scope
fields after dot
methods after dot
importable modules if known
```

Keyword completions:

```text
fun
struct
enum
trait
impl
actor
typealias
const
import
from
as
let
var
return
if
else
match
while
for
in
break
continue
async
await
spawn
go
self
true
false
chan
pub
```

For dot completion:

```myla
value.
```

Ask the compiler/typechecker for the type of `value`, then return fields/methods.

Do not overinvest in completion until diagnostics and definition are stable.

---

# Phase 10: Formatting

The current VS Code extension has a placeholder format command.

Replace it with either:

```text
LSP textDocument/formatting
```

or:

```text
VS Code DocumentFormattingEditProvider
```

Preferred: LSP.

Compiler/tooling API:

```python
def format_file(path: str, source: str) -> str:
    ...
```

LSP should return a single full-document replacement edit initially:

```python
TextEdit(
    range=full_document_range,
    new_text=formatted_source,
)
```

Later, optimize if needed.

---

# Phase 11: Semantic tokens

Keep TextMate highlighting as the fallback.

Add semantic tokens only after name resolution/type checking is accessible.

Semantic token categories to support:

```text
function
method
type
class / struct
enum
enumMember
interface / trait
parameter
variable
property / field
keyword
operator
number
string
comment
macro/decorator if attributes behave that way
```

Useful Myla-specific semantic distinction:

```text
function declaration vs function call
type name vs variable name
trait method vs impl method
field access vs local variable
parameter vs local
const vs mutable var
```

---

# Extension-side commands to keep or update

Current placeholder commands should become:

```text
Myla: Show Extension Info
Myla: Restart Language Server
Myla: Format File
Myla: Show Compiler Version
```

Implement:

```ts
myla.restartLanguageServer
```

by stopping and starting the LanguageClient.

Implement:

```ts
myla.showCompilerVersion
```

by asking the server via custom request or running:

```bash
myla --version
```

---

# Error handling requirements

The language server must never crash because user code has syntax errors.

Handle these cases gracefully:

```text
compiler import fails
compiler path is wrong
Python executable missing
workspace has no Myla compiler configured
compiler throws internal exception
file is unsaved / untitled
source has syntax errors
diagnostic range is missing
diagnostic range is outside document bounds
```

If the server cannot start, show a VS Code error like:

```text
Could not start Myla language server. Check myla.pythonPath and myla.compilerPath.
```

If the compiler crashes, publish one diagnostic at the top of the file:

```text
Internal compiler error while checking this file: ...
```

and log the traceback to the language server output channel.

---

# Logging

Add an output channel in the VS Code extension:

```ts
const outputChannel = vscode.window.createOutputChannel("Myla");
```

Pass it to the language client if useful.

The Python server should log to stderr, not stdout, because stdout is used for LSP communication.

Log:

```text
server startup
compiler path
workspace root
diagnostic runs
compiler exceptions
request failures
```

Do not spam logs on every keystroke unless verbose mode is enabled.

---

# Testing plan

## Manual tests

Create a `test.my` file with a valid program.

Expected:

```text
No diagnostics.
Syntax highlighting works.
Snippets work.
```

Create a syntax error.

Expected:

```text
Red squiggle at the correct range.
Problems panel shows compiler message.
Saving and editing update diagnostics.
```

Create a type error.

Expected:

```text
Red squiggle at the type error location.
Compiler message appears unchanged or lightly adapted.
```

Create an undefined name.

Expected:

```text
Red squiggle under the unknown identifier.
```

Later, for definition:

```myla
fun add(a: Int, b: Int) -> Int {
    return a + b
}

fun main() {
    let x = add(1, 2)
}
```

Ctrl+click on `add` in `main` should jump to the function declaration.

## Automated tests

Add Python tests for:

```text
compiler_adapter.check_file
diagnostic conversion
line/column conversion
URI/path conversion
```

Add VS Code extension integration tests later if desired.

---

# Recommended first development milestone

The first concrete milestone should be:

```text
Opening a .my file in VS Code runs the Python compiler and shows diagnostics in the editor.
```

Acceptance criteria:

```text
1. Extension starts Python LSP server automatically for .my files.
2. LSP server receives didOpen and didChange events.
3. LSP server calls Python compiler on current in-memory source.
4. Compiler errors appear as VS Code diagnostics.
5. Diagnostics clear when the code is fixed.
6. Server logs useful errors without crashing.
```

Do not start with Go to Definition. It is more complex because it needs symbol resolution and source locations. Diagnostics will prove that the VS Code extension, Python server, compiler adapter, and document synchronization are all wired correctly.

---

# Recommended second milestone

After diagnostics:

```text
Add top-level document symbols.
```

Acceptance criteria:

```text
The VS Code Outline panel lists:
functions
structs
enums
traits
impls
actors
type aliases
constants
```

This can be implemented using either:

```text
compiler AST
Tree-sitter parse
a lightweight parser
```

Prefer compiler AST if source locations are available.

---

# Recommended third milestone

Then implement simple top-level Go to Definition.

Acceptance criteria:

```text
Ctrl+click on a top-level function call jumps to the function declaration.
Ctrl+click on a struct/type name jumps to its declaration.
Ctrl+click on a const name jumps to its declaration.
```

This can initially use a workspace symbol index before full type-aware resolution exists.

---

# Summary for the implementer

Build a Python LSP server that wraps the existing bootstrapping compiler. Start by exposing structured compiler diagnostics, then wire the VS Code extension to start the server over stdio. Do not reimplement Myla parsing in TypeScript. Keep TextMate highlighting and snippets as they are. Add editor intelligence incrementally, with diagnostics first, then symbols, then definition/hover/completion.
