---
id: MYLA-245
title: "Toolchain modularity: core std, official packages, the compiler as packages"
type: design
status: backlog
priority: medium
labels: [design, stdlib, project-tool, platforms]
---
From the owner's discussion of 2026-11-02, alongside D117: the toolchain must not grow into one unmanageable binary out of one pipeline. A design round, recorded as a decision.

- [ ] **What std is:** a small, portable core embedded in the toolchain ([[MYLA-243]]): collections, strings, I/O, files, processes, json/toml, tasks; what belongs there and what doesn't
- [ ] **Official packages beside it:** the GUI ([[MYLA-63]]), HTTP and the like as packages of their own with their own versions, fetched as any dependency is ([[Architecture/Project-tool]]), later from a registry; the owner leaned toward GUI code in std for its many native interfaces, the recommendation was packages plus the C FFI ([[MYLA-166]]) and code chosen per target
- [ ] **Code per target:** a way to pick declarations per platform (like Rust's `#[cfg(target_os = …)]`), which std's platform layer ([[MYLA-162]]) and those packages both need
- [ ] **Precompiled modules:** shipping std (and packages) as checked, still generic modules plus their interfaces instead of source, keyed to the compiler build that reads them, once measurements show std's size in build times; sources still shipped for the language server and diagnostics
- [ ] **The compiler as packages:** the front end (lexer, parser, checker, loader), the IR, each backend, the language server and the tools as packages with clear interfaces, built from one repository

## From the new targets (2026-11-04, [[Project/Reflection-2026-11]])

- Code per target is needed now: the loader substitutes a whole file for `std/platform.my` per target (`for_target` in [[selfhost/loader.my]]), the smallest form that worked for aarch64 and wasm. macOS and Windows, std's capabilities that differ per target ([[MYLA-266]]) and programs that want to know their target all need declarations chosen per target.
- What a backend brings: about 1,500 lines of translation, a runtime file of 500–600 lines, a platform module and its tools. [[MYLA-262]] puts that behind one target description, which makes "each backend a package" a matter of where the files live.
- The page's toolchain (`play.wasm`, about 2 MB) is the checker and the interpreter without the backends: the first build of the compiler made of fewer parts.
