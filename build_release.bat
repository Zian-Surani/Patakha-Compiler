@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_windows_release.ps1 -OneFile
