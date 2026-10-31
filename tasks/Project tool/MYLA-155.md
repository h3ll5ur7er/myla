---
id: MYLA-155
title: Language server - Git dependencies of a checkout, and myla.toml documents
type: improvement
status: backlog
priority: low
labels: [lsp, project-tool]
---
Split from [[MYLA-97]], whose two open points nothing else tracks:

- [ ] A Git dependency's own Git dependencies are checked out under the root package's `.myla/deps/`. Opening a file of a Git checkout makes the checkout's `myla.toml` the project, whose dependencies then show as not checked out: the server should remember which project led there
- [ ] An open `myla.toml` isn't checked itself (the extension's client syncs only `myla` documents): its diagnostics should reach it directly
