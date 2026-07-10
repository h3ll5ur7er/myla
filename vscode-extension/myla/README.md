# Myla Language Support

VS Code language support for the Myla programming language.

## Features

- TextMate syntax highlighting for `.my` files
- Comment toggling for `//` and `/* ... */`
- Bracket matching and auto-closing pairs
- Region folding with `// region` / `// endregion` and `// #region` / `// #endregion`
- Snippets for common Myla constructs
- Extension activation scaffold for future language-server integration
- Placeholder `Myla: Format File` command

## Development

Install dependencies:

```bash
npm install
```

Compile the extension:

```bash
npm run compile
```

Open this folder in VS Code and press `F5` to launch an Extension Development Host.

## Useful commands while developing

- `Developer: Inspect Editor Tokens and Scopes`
- `Myla: Show Extension Info`
- `Myla: Format File`

## Notes

The highlighting is currently TextMate-based so it works through VS Code's standard syntax highlighting pipeline. The `src/extension.ts` scaffold is intentionally small and ready for the next step: connecting a Myla language server.
