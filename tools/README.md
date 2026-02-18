# tools/

Utility scripts and local VS Code extension assets.

## Contents

- `install_patakha_extension.ps1`: package/install local VS Code language extension.
- `build_windows_release.ps1`: build Windows-ready CLI + Studio executables and zip bundle.
- `vscode-patakha-language/`: extension source (grammar, snippets, language config).

## Install Local Extension

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_patakha_extension.ps1 -Force
```

After install, reload VS Code window if colors/snippets do not appear.

## Windows Release Build

Requires:
- `pyinstaller` (`pip install pyinstaller`)
- Optional: Inno Setup (`iscc`) for installer `.exe` generation

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_windows_release.ps1 -OneFile
```

Or from repo root:

```bat
build_release.bat
```

If Inno Setup is installed, the script also produces `Patakha-Setup.exe` using `tools/patakha_installer.iss`.
