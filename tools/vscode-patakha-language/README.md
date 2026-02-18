# Patakha VS Code Language Extension

This folder contains a local VS Code extension scaffold for Patakha (`.bhai`) with:

- Syntax highlighting (TextMate grammar)
- Bracket/comment language config
- Starter snippets

## Local Development

1. Open this folder in VS Code:
   - `tools/vscode-patakha-language`
2. Press `F5` to launch an Extension Development Host.
3. Open any `.bhai` file in the dev host and check highlighting/snippets.

## Package as VSIX

1. Install `vsce`:
   - `npm i -g @vscode/vsce`
2. From this folder run:
   - `vsce package`
3. Install generated `.vsix` via:
   - Command Palette -> `Extensions: Install from VSIX...`

After installation, set `.bhai` files to language mode `Patakha` if needed.
