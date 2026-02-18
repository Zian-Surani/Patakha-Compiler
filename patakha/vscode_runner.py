from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from patakha.compiler import compile_source
from patakha.diagnostics import PatakhaAggregateError, PatakhaError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="patakha-vscode-runner",
        description="Compile and run a Patakha source file from VS Code.",
    )
    parser.add_argument("source", help="Path to .bhai source file")
    parser.add_argument("--no-opt", action="store_true", help="Disable IR optimization")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_path = Path(args.source)

    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read source file `{source_path}`: {exc}", file=sys.stderr)
        return 1

    try:
        result = compile_source(source_text, optimize=not args.no_opt, source_name=source_path)
    except PatakhaAggregateError as exc:
        print(exc.pretty(str(source_path), source_text=source_text), file=sys.stderr)
        return 1
    except PatakhaError as exc:
        print(exc.pretty(str(source_path), source_text=source_text), file=sys.stderr)
        return 1

    for warning in result.semantic.warnings:
        print(warning.pretty(str(source_path)), flush=True)

    c_path = source_path.with_suffix(".c")
    exe_path = _exe_path(source_path)
    c_path.write_text(result.c_code, encoding="utf-8")
    print(f"[ok] C code generated: {c_path}", flush=True)

    try:
        gcc = subprocess.run(
            ["gcc", str(c_path), "-o", str(exe_path)],
            check=False,
        )
    except FileNotFoundError:
        print("`gcc` not found in PATH. Install GCC/MinGW first.", file=sys.stderr)
        return 1

    if gcc.returncode != 0:
        return gcc.returncode

    print(f"[ok] Executable generated: {exe_path}", flush=True)
    try:
        run = subprocess.run([str(exe_path)], check=False)
    except FileNotFoundError:
        print(f"Could not run executable: {exe_path}", file=sys.stderr)
        return 1
    return run.returncode


def _exe_path(source_path: Path) -> Path:
    if os.name == "nt":
        return source_path.with_suffix(".exe")
    return Path(str(source_path.with_suffix("")))


if __name__ == "__main__":
    raise SystemExit(main())
