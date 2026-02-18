from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from patakha.compiler import compile_source
from patakha.formatter import format_program
from patakha.lexer import Lexer
from patakha.parser import Parser
from patakha.semantic import SemanticAnalyzer


@dataclass
class LintIssue:
    severity: str  # "warning" | "info"
    code: str
    message: str
    line: int
    column: int


def lint_source(source: str, source_name: str | Path | None = None) -> list[LintIssue]:
    tokens = Lexer(source).tokenize()
    issues: list[LintIssue] = []

    keyword_aliases = {
        ("START_BHAI", "start_bhai"): "shuru",
        ("BAS_KAR", "bas_kar"): "bass",
        ("IMPORT", "laao"): "import",
        ("DECIMAL", "float"): "decimal",
        ("FOR", "for"): "jabtak",
        ("JABTAK", "while"): "tabtak",
        ("DO", "do"): "kar",
        ("BREAK", "break"): "tod",
        ("CONTINUE", "continue"): "jari",
        ("CLASS", "class"): "kaksha",
        ("VOID", "void"): "khali",
    }
    for i, tok in enumerate(tokens):
        key = (tok.kind, str(tok.value))
        preferred = keyword_aliases.get(key)
        if preferred is not None:
            issues.append(
                LintIssue(
                    severity="warning",
                    code="legacy_keyword",
                    message=f"Use `{preferred}` instead of legacy `{tok.value}`.",
                    line=tok.line,
                    column=tok.column,
                )
            )
        if tok.kind == "IDENT" and str(tok.value) == "input":
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if nxt is not None and nxt.kind == "LPAREN":
                issues.append(
                    LintIssue(
                        severity="warning",
                        code="legacy_builtin",
                        message="Use `bata()` instead of legacy `input()`.",
                        line=tok.line,
                        column=tok.column,
                    )
                )

    source_lines = source.splitlines()
    for i, line in enumerate(source_lines, start=1):
        if line.rstrip(" \t") != line:
            issues.append(
                LintIssue(
                    severity="info",
                    code="trailing_whitespace",
                    message="Line has trailing whitespace.",
                    line=i,
                    column=max(len(line), 1),
                )
            )
    if source and not source.endswith("\n"):
        issues.append(
            LintIssue(
                severity="info",
                code="final_newline",
                message="File should end with newline.",
                line=max(len(source_lines), 1),
                column=max(len(source_lines[-1]) + 1 if source_lines else 1, 1),
            )
        )

    ast = Parser(tokens).parse()
    if source_name is not None:
        compiled = compile_source(source, source_name=source_name)
        semantic = compiled.semantic
    else:
        semantic = SemanticAnalyzer().analyze(ast)
    for warning in semantic.warnings:
        issues.append(
            LintIssue(
                severity="warning",
                code=warning.code,
                message=warning.message,
                line=warning.line,
                column=warning.column,
            )
        )

    formatted = format_program(ast)
    if formatted != source:
        issues.append(
            LintIssue(
                severity="info",
                code="format",
                message="Formatting differs from canonical `patakha fmt` style.",
                line=1,
                column=1,
            )
        )

    issues.sort(key=lambda x: (x.line, x.column, 0 if x.severity == "warning" else 1, x.code))
    return issues


def format_lint_issues(source_name: str, issues: list[LintIssue]) -> str:
    if not issues:
        return f"{source_name}: no lint issues found.\n"
    rows: list[str] = []
    for issue in issues:
        rows.append(
            f"{source_name}:{issue.line}:{issue.column} [{issue.severity}:{issue.code}] {issue.message}"
        )
    return "\n".join(rows) + "\n"
