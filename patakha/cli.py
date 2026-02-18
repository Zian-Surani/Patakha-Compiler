from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from patakha.compiler import (
    compile_source,
    format_ast,
    format_ast_dot,
    format_cfg,
    format_cfg_dot,
    format_ir,
    format_symbols,
    format_tokens,
)
from patakha.diagnostics import PatakhaAggregateError, PatakhaError
from patakha.formatter import format_source
from patakha.interpreter import run_program
from patakha.lint import format_lint_issues, lint_source
from patakha.ll1 import build_ll1_artifacts, format_ll1_artifacts, predictive_parse_trace
from patakha.slr_lab import build_demo_slr, format_slr_artifacts, slr_parse_trace


def build_compile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patakha",
        description="Patakha compiler",
    )
    parser.add_argument("source", help="Path to .bhai source file")
    parser.add_argument(
        "-o",
        "--output",
        help="Output path (default: .c for C backend, .stk for stack backend)",
    )
    parser.add_argument(
        "--backend",
        choices=["c", "stack"],
        default="c",
        help="Primary backend output",
    )
    parser.add_argument("--no-opt", action="store_true", help="Disable IR optimization")
    parser.add_argument("--emit-warnings", action="store_true", help="Write warnings to <source>.warnings.txt")
    parser.add_argument("--emit-tokens", action="store_true", help="Write tokens to <source>.tokens.txt")
    parser.add_argument("--emit-ir", action="store_true", help="Write optimized IR to <source>.ir")
    parser.add_argument("--emit-raw-ir", action="store_true", help="Write pre-optimization IR to <source>.raw.ir")
    parser.add_argument("--emit-stack", action="store_true", help="Write stack backend code to <source>.stk")
    parser.add_argument("--dump-ast", action="store_true", help="Write AST tree to <source>.ast.txt")
    parser.add_argument("--dump-ast-dot", action="store_true", help="Write AST dot graph to <source>.ast.dot")
    parser.add_argument("--dump-symbols", action="store_true", help="Write symbol table dump to <source>.symbols.txt")
    parser.add_argument("--dump-cfg", action="store_true", help="Write CFG dump to <source>.cfg.txt")
    parser.add_argument("--dump-cfg-dot", action="store_true", help="Write CFG dot graph to <source>.cfg.dot")
    parser.add_argument("--dump-ll1", action="store_true", help="Write LL(1) FIRST/FOLLOW/table to <source>.ll1.txt")
    parser.add_argument("--dump-slr", action="store_true", help="Write SLR lab module output to <source>.slr.txt")
    parser.add_argument("--gcc", action="store_true", help="Compile generated C with gcc (C backend only)")
    parser.add_argument("--exe", help="Executable path for --gcc (default: source stem)")
    return parser


def main_compile(argv: list[str] | None = None) -> int:
    parser = build_compile_parser()
    args = parser.parse_args(argv)
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

    if result.semantic.warnings:
        for w in result.semantic.warnings:
            print(w.pretty(str(source_path)))

    if args.backend == "c":
        out_path = Path(args.output) if args.output else source_path.with_suffix(".c")
        out_path.write_text(result.c_code, encoding="utf-8")
        print(f"[ok] C code generated: {out_path}")
    else:
        out_path = Path(args.output) if args.output else source_path.with_suffix(".stk")
        out_path.write_text(result.stack_code, encoding="utf-8")
        print(f"[ok] Stack code generated: {out_path}")

    if args.emit_warnings:
        warn_path = source_path.with_suffix(".warnings.txt")
        if result.semantic.warnings:
            warn_text = "\n".join(w.pretty(str(source_path)) for w in result.semantic.warnings) + "\n"
        else:
            warn_text = "<no warnings>\n"
        warn_path.write_text(warn_text, encoding="utf-8")
        print(f"[ok] Warnings written: {warn_path}")

    if args.emit_tokens:
        token_path = source_path.with_suffix(".tokens.txt")
        token_path.write_text(format_tokens(result.tokens), encoding="utf-8")
        print(f"[ok] Tokens written: {token_path}")

    if args.emit_ir:
        ir_path = source_path.with_suffix(".ir")
        ir_path.write_text(format_ir(result.ir_optimized), encoding="utf-8")
        print(f"[ok] IR written: {ir_path}")

    if args.emit_raw_ir:
        raw_ir_path = source_path.with_suffix(".raw.ir")
        raw_ir_path.write_text(format_ir(result.ir_raw), encoding="utf-8")
        print(f"[ok] Raw IR written: {raw_ir_path}")

    if args.emit_stack:
        stk_path = source_path.with_suffix(".stk")
        stk_path.write_text(result.stack_code, encoding="utf-8")
        print(f"[ok] Stack code written: {stk_path}")

    if args.dump_ast:
        ast_path = source_path.with_suffix(".ast.txt")
        ast_path.write_text(format_ast(result.ast), encoding="utf-8")
        print(f"[ok] AST written: {ast_path}")

    if args.dump_ast_dot:
        ast_dot_path = source_path.with_suffix(".ast.dot")
        ast_dot_path.write_text(format_ast_dot(result.ast), encoding="utf-8")
        print(f"[ok] AST dot written: {ast_dot_path}")

    if args.dump_symbols:
        sym_path = source_path.with_suffix(".symbols.txt")
        sym_path.write_text(format_symbols(result.semantic), encoding="utf-8")
        print(f"[ok] Symbols written: {sym_path}")

    if args.dump_cfg:
        cfg_path = source_path.with_suffix(".cfg.txt")
        cfg_path.write_text(format_cfg(result.cfg_by_function), encoding="utf-8")
        print(f"[ok] CFG written: {cfg_path}")

    if args.dump_cfg_dot:
        cfg_dot_path = source_path.with_suffix(".cfg.dot")
        cfg_dot_path.write_text(format_cfg_dot(result.cfg_by_function), encoding="utf-8")
        print(f"[ok] CFG dot written: {cfg_dot_path}")

    if args.dump_ll1:
        ll1_artifacts = build_ll1_artifacts()
        trace = predictive_parse_trace([tok.kind for tok in result.tokens], ll1_artifacts)
        ll1_path = source_path.with_suffix(".ll1.txt")
        ll1_path.write_text(format_ll1_artifacts(ll1_artifacts, trace), encoding="utf-8")
        print(f"[ok] LL1 artifacts written: {ll1_path}")

    if args.dump_slr:
        slr_artifacts = build_demo_slr()
        demo_trace = slr_parse_trace(["id", "+", "id", "*", "id"], slr_artifacts)
        slr_path = source_path.with_suffix(".slr.txt")
        slr_path.write_text(format_slr_artifacts(slr_artifacts, demo_trace), encoding="utf-8")
        print(f"[ok] SLR artifacts written: {slr_path}")

    if args.gcc:
        if args.backend != "c":
            print("--gcc works only with --backend c", file=sys.stderr)
            return 1
        c_path = Path(args.output) if args.output else source_path.with_suffix(".c")
        if args.exe:
            exe_path = Path(args.exe)
        else:
            exe_path = (
                source_path.with_suffix(".exe")
                if os.name == "nt"
                else Path(str(source_path.with_suffix("")))
            )
        try:
            subprocess.run(
                ["gcc", str(c_path), "-o", str(exe_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            print("`gcc` not found in PATH. Install GCC/MinGW first.", file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as exc:
            print("gcc compilation failed:", file=sys.stderr)
            if exc.stdout:
                print(exc.stdout, file=sys.stderr)
            if exc.stderr:
                print(exc.stderr, file=sys.stderr)
            return 1
        print(f"[ok] Executable generated: {exe_path}")

    return 0


def build_fmt_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patakha fmt",
        description="Format Patakha source using canonical style.",
    )
    parser.add_argument("source", help="Path to .bhai source file")
    parser.add_argument("-w", "--write", action="store_true", help="Write formatted output to source file")
    parser.add_argument("--check", action="store_true", help="Exit non-zero if formatting changes are needed")
    parser.add_argument("--stdout", action="store_true", help="Print formatted output to stdout")
    return parser


def main_fmt(argv: list[str] | None = None) -> int:
    parser = build_fmt_parser()
    args = parser.parse_args(argv)
    source_path = Path(args.source)

    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read source file `{source_path}`: {exc}", file=sys.stderr)
        return 1

    try:
        formatted = format_source(source_text)
    except PatakhaAggregateError as exc:
        print(exc.pretty(str(source_path), source_text=source_text), file=sys.stderr)
        return 1
    except PatakhaError as exc:
        print(exc.pretty(str(source_path), source_text=source_text), file=sys.stderr)
        return 1

    changed = formatted != source_text
    if args.check:
        if changed:
            print(f"[fmt] needs formatting: {source_path}")
            return 1
        print(f"[fmt] already formatted: {source_path}")
        return 0

    if args.stdout:
        print(formatted, end="")
        return 0

    write_in_place = args.write or (not args.check and not args.stdout)
    if write_in_place:
        source_path.write_text(formatted, encoding="utf-8")
        if changed:
            print(f"[fmt] formatted: {source_path}")
        else:
            print(f"[fmt] no changes: {source_path}")
    return 0


def build_lint_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patakha lint",
        description="Lint Patakha source and report warnings/style issues.",
    )
    parser.add_argument("source", help="Path to .bhai source file")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any warning/info issue is found.",
    )
    return parser


def build_repl_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="patakha repl",
        description="Run Patakha REPL / scratchpad mode.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="Optional .bhai file to preload into REPL buffer.",
    )
    return parser


def main_lint(argv: list[str] | None = None) -> int:
    parser = build_lint_parser()
    args = parser.parse_args(argv)
    source_path = Path(args.source)

    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Could not read source file `{source_path}`: {exc}", file=sys.stderr)
        return 1

    try:
        issues = lint_source(source_text, source_name=source_path)
    except PatakhaAggregateError as exc:
        print(exc.pretty(str(source_path), source_text=source_text), file=sys.stderr)
        return 1
    except PatakhaError as exc:
        print(exc.pretty(str(source_path), source_text=source_text), file=sys.stderr)
        return 1

    report = format_lint_issues(str(source_path), issues)
    print(report, end="")

    warning_or_info = any(issue.severity in {"warning", "info"} for issue in issues)
    if args.strict and warning_or_info:
        return 1
    return 0


def main_repl(argv: list[str] | None = None) -> int:
    parser = build_repl_parser()
    args = parser.parse_args(argv)

    buffer: list[str] = []
    source_name = Path.cwd() / "__repl__.bhai"
    if args.source:
        source_path = Path(args.source)
        try:
            preloaded = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Could not read source file `{source_path}`: {exc}", file=sys.stderr)
            return 1
        buffer = preloaded.splitlines()
        source_name = source_path.resolve()

    print("Patakha REPL. Type :help for commands.")
    while True:
        prompt = "patakha> " if not buffer else "... "
        try:
            line = input(prompt)
        except EOFError:
            print("")
            return 0
        except KeyboardInterrupt:
            print("")
            return 0

        command = line.strip()
        if command == ":quit":
            return 0
        if command == ":help":
            print(":run   compile + interpret current buffer")
            print(":show  print current buffer")
            print(":clear clear current buffer")
            print(":quit  exit repl")
            continue
        if command == ":show":
            if not buffer:
                print("<empty>")
            else:
                print("\n".join(buffer))
            continue
        if command == ":clear":
            buffer.clear()
            print("[ok] buffer cleared")
            continue
        if command == ":run":
            source_text = "\n".join(buffer).strip()
            if not source_text:
                print("[info] buffer is empty")
                continue
            if "shuru" not in source_text and "start_bhai" not in source_text:
                source_text = "shuru\n" + source_text + "\nbass\n"
            try:
                result = compile_source(source_text, source_name=source_name)
                run_program(result.ast, result.semantic)
            except PatakhaAggregateError as exc:
                print(exc.pretty(str(source_name), source_text=source_text), file=sys.stderr)
            except PatakhaError as exc:
                print(exc.pretty(str(source_name), source_text=source_text), file=sys.stderr)
            continue

        buffer.append(line)


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    if args and args[0] in {"compile", "fmt", "lint", "repl"}:
        cmd = args[0]
        rest = args[1:]
    else:
        cmd = "compile"
        rest = args

    if cmd == "compile":
        return main_compile(rest)
    if cmd == "fmt":
        return main_fmt(rest)
    if cmd == "lint":
        return main_lint(rest)
    if cmd == "repl":
        return main_repl(rest)
    return 1
