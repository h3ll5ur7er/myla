"""Allow `python -m myla.lsp` to launch the language server."""
from .server import main

raise SystemExit(main())
