---
id: MYLA-739
title: "The website's downloads offer myla.exe"
type: feature
status: backlog
priority: low
labels: [website, ci, windows]
---
Found while building [[MYLA-708]]. On a push to master CI's `windows` job uploads `myla.exe` and `myla-lsp.exe` as the artifact `myla-x86_64-windows-<sha>` (a zip of the two, as an artifact is; D207), but the `pages` job downloads only `myla-*-linux-<sha>` and the vsix, and `website/scripts/downloads.mjs` knows `x86_64-linux`, `aarch64-linux` and `vscode` (`myla-<platform>.tar.gz`): the downloads page has no Windows build.

- [ ] `pages` needs `windows` and downloads its artifact; `downloads.mjs` names a `x86_64-windows` platform (a `.zip`, not a tarball) and the page offers it
