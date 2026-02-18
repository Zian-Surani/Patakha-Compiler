from __future__ import annotations

from patakha.ast_nodes import (
    Assign,
    Binary,
    Block,
    BreakStmt,
    Cast,
    Call,
    ContinueStmt,
    DoWhileStmt,
    Expr,
    ExprStmt,
    ForStmt,
    FunctionDecl,
    Identifier,
    IfStmt,
    IndexAccess,
    Literal,
    MemberAccess,
    PrintStmt,
    Program,
    ReturnStmt,
    Stmt,
    SwitchStmt,
    TypeDecl,
    Unary,
    VarDecl,
    WhileStmt,
)
from patakha.lexer import Lexer
from patakha.parser import Parser


INDENT = " " * 4


def format_source(source: str) -> str:
    tokens = Lexer(source).tokenize()
    program = Parser(tokens).parse()
    return format_program(program)


def format_program(program: Program) -> str:
    lines: list[str] = []

    for imp in program.imports:
        lines.append(f"import {_quote_string(imp)}")
    if program.imports:
        lines.append("")

    for decl in program.type_decls:
        _emit_type_decl(lines, decl)
        lines.append("")

    for fn in program.functions:
        _emit_function(lines, fn)
        lines.append("")

    lines.append("shuru")
    for stmt in program.statements:
        _emit_stmt(lines, stmt, 0)
    lines.append("bass")
    return "\n".join(lines) + "\n"


def _emit_type_decl(lines: list[str], decl: TypeDecl) -> None:
    kind_text = "kaksha" if decl.kind == "class" else decl.kind
    lines.append(f"{kind_text} {decl.name} {{")
    for field in decl.fields:
        suffix = f"[{field.array_size}]" if field.array_size is not None else ""
        lines.append(f"{INDENT}{_type_text(field.type_name)} {field.name}{suffix};")
    lines.append("};")


def _emit_function(lines: list[str], fn: FunctionDecl) -> None:
    params = fn.typed_params or []
    if params:
        params_text = ", ".join(f"{_type_text(p.type_name)} {p.name}" for p in params)
    else:
        params_text = ", ".join(f"bhai {name}" for name in fn.params)
    lines.append(f"kaam {_type_text(fn.return_type)} {fn.name}({params_text}) {{")
    for stmt in fn.body.statements:
        _emit_stmt(lines, stmt, 1)
    lines.append("}")


def _emit_stmt(lines: list[str], stmt: Stmt, depth: int) -> None:
    pad = INDENT * depth

    if isinstance(stmt, VarDecl):
        suffix = f"[{stmt.array_size}]" if stmt.array_size is not None else ""
        if stmt.init is None:
            lines.append(f"{pad}{_type_text(stmt.type_name)} {stmt.name}{suffix};")
        else:
            lines.append(
                f"{pad}{_type_text(stmt.type_name)} {stmt.name}{suffix} = {_format_expr(stmt.init)};"
            )
        return

    if isinstance(stmt, Assign):
        target = stmt.target if stmt.target is not None else Identifier(stmt.name, stmt.line, stmt.column)
        lines.append(f"{pad}{_format_expr(target)} = {_format_expr(stmt.value)};")
        return

    if isinstance(stmt, IfStmt):
        lines.append(f"{pad}agar ({_format_expr(stmt.condition)}) {{")
        for inner in stmt.then_block.statements:
            _emit_stmt(lines, inner, depth + 1)
        lines.append(f"{pad}}}")
        if stmt.else_block is not None:
            lines.append(f"{pad}warna {{")
            for inner in stmt.else_block.statements:
                _emit_stmt(lines, inner, depth + 1)
            lines.append(f"{pad}}}")
        return

    if isinstance(stmt, WhileStmt):
        lines.append(f"{pad}tabtak ({_format_expr(stmt.condition)}) {{")
        for inner in stmt.body.statements:
            _emit_stmt(lines, inner, depth + 1)
        lines.append(f"{pad}}}")
        return

    if isinstance(stmt, ForStmt):
        init = _format_for_part(stmt.init)
        cond = _format_expr(stmt.condition) if stmt.condition is not None else ""
        post = _format_for_part(stmt.post)
        lines.append(f"{pad}jabtak ({init}; {cond}; {post}) {{")
        for inner in stmt.body.statements:
            _emit_stmt(lines, inner, depth + 1)
        lines.append(f"{pad}}}")
        return

    if isinstance(stmt, DoWhileStmt):
        lines.append(f"{pad}kar {{")
        for inner in stmt.body.statements:
            _emit_stmt(lines, inner, depth + 1)
        lines.append(f"{pad}}} tabtak ({_format_expr(stmt.condition)});")
        return

    if isinstance(stmt, SwitchStmt):
        lines.append(f"{pad}switch ({_format_expr(stmt.condition)}) {{")
        for case in stmt.cases:
            lines.append(f"{pad}{INDENT}case {_format_expr(case.value)}:")
            for inner in case.block.statements:
                _emit_stmt(lines, inner, depth + 2)
        if stmt.default_block is not None:
            lines.append(f"{pad}{INDENT}default:")
            for inner in stmt.default_block.statements:
                _emit_stmt(lines, inner, depth + 2)
        lines.append(f"{pad}}}")
        return

    if isinstance(stmt, BreakStmt):
        lines.append(f"{pad}tod;")
        return

    if isinstance(stmt, ContinueStmt):
        lines.append(f"{pad}jari;")
        return

    if isinstance(stmt, PrintStmt):
        lines.append(f"{pad}bol({_format_expr(stmt.value)});")
        return

    if isinstance(stmt, ReturnStmt):
        if stmt.value is None:
            lines.append(f"{pad}nikal;")
        else:
            lines.append(f"{pad}nikal {_format_expr(stmt.value)};")
        return

    if isinstance(stmt, ExprStmt):
        lines.append(f"{pad}{_format_expr(stmt.expr)};")
        return

    if isinstance(stmt, Block):
        lines.append(f"{pad}{{")
        for inner in stmt.statements:
            _emit_stmt(lines, inner, depth + 1)
        lines.append(f"{pad}}}")


def _format_for_part(stmt: Stmt | None) -> str:
    if stmt is None:
        return ""
    if isinstance(stmt, VarDecl):
        suffix = f"[{stmt.array_size}]" if stmt.array_size is not None else ""
        if stmt.init is None:
            return f"{_type_text(stmt.type_name)} {stmt.name}{suffix}"
        return f"{_type_text(stmt.type_name)} {stmt.name}{suffix} = {_format_expr(stmt.init)}"
    if isinstance(stmt, Assign):
        target = stmt.target if stmt.target is not None else Identifier(stmt.name, stmt.line, stmt.column)
        return f"{_format_expr(target)} = {_format_expr(stmt.value)}"
    if isinstance(stmt, ExprStmt):
        return _format_expr(stmt.expr)
    return ""


def _format_expr(expr: Expr) -> str:
    if isinstance(expr, Identifier):
        return expr.name
    if isinstance(expr, Literal):
        if isinstance(expr.value, bool):
            return "sach" if expr.value else "jhooth"
        if isinstance(expr.value, float):
            text = f"{expr.value:g}"
            if "." not in text and "e" not in text and "E" not in text:
                text += ".0"
            return text
        if isinstance(expr.value, int):
            return str(expr.value)
        return _quote_string(str(expr.value))
    if isinstance(expr, Unary):
        return f"{expr.op}{_format_expr(expr.operand)}"
    if isinstance(expr, Binary):
        return f"({_format_expr(expr.left)} {expr.op} {_format_expr(expr.right)})"
    if isinstance(expr, Call):
        args = ", ".join(_format_expr(arg) for arg in expr.args)
        return f"{expr.callee}({args})"
    if isinstance(expr, IndexAccess):
        return f"{_format_expr(expr.base)}[{_format_expr(expr.index)}]"
    if isinstance(expr, MemberAccess):
        return f"{_format_expr(expr.base)}.{expr.member}"
    if isinstance(expr, Cast):
        return f"{_type_text(expr.type_name)}({_format_expr(expr.expr)})"
    return "0"


def _type_text(type_name: str) -> str:
    if type_name == "int":
        return "bhai"
    if type_name == "float":
        return "decimal"
    if type_name == "bool":
        return "bool"
    if type_name == "text":
        return "text"
    if type_name == "void":
        return "khali"
    return type_name


def _quote_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f"\"{escaped}\""
