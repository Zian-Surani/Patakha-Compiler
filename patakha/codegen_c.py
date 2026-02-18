from __future__ import annotations

from dataclasses import dataclass

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
    SwitchStmt,
    TypeDecl,
    Unary,
    VarDecl,
    WhileStmt,
)
from patakha.semantic import SemanticResult


@dataclass
class CGenState:
    lines: list[str]
    indent: int = 0
    uses_input: bool = False

    def emit(self, line: str = "") -> None:
        self.lines.append(("    " * self.indent) + line)


def generate_c_code(program: Program, semantic: SemanticResult) -> str:
    state = CGenState(lines=[])
    state.emit("#include <stdio.h>")
    state.emit("#include <string.h>")
    state.emit("")

    for decl in program.type_decls:
        _emit_type_decl(state, decl, semantic)
        state.emit("")

    for fn in program.functions:
        state.emit(_function_signature(fn, semantic) + ";")
    if program.functions:
        state.emit("")

    for fn in program.functions:
        _emit_function(state, fn, semantic)
        state.emit("")

    state.emit("int main(void) {")
    state.indent += 1
    for stmt in program.statements:
        _emit_stmt(state, stmt, semantic)
    state.indent -= 1
    state.emit("}")

    if state.uses_input:
        helper = [
            "",
            "static int patakha_input_int(void) {",
            "    int _v = 0;",
            "    if (scanf(\"%d\", &_v) != 1) return 0;",
            "    return _v;",
            "}",
        ]
        out = "\n".join(state.lines)
        insert_at = out.find("\n\n")
        if insert_at == -1:
            out = out + "\n" + "\n".join(helper)
        else:
            out = out[:insert_at] + "\n" + "\n".join(helper) + out[insert_at:]
        return out + "\n"

    return "\n".join(state.lines) + "\n"


def _emit_type_decl(state: CGenState, decl: TypeDecl, semantic: SemanticResult) -> None:
    kind = "struct"
    state.emit(f"typedef {kind} {decl.name} {{")
    state.indent += 1
    fields = semantic.composite_fields.get(decl.name, {})
    for f in decl.fields:
        field_type = fields.get(f.name, "int")
        state.emit(_decl_for_type(field_type, f.name) + ";")
    state.indent -= 1
    state.emit(f"}} {decl.name};")


def _function_signature(fn: FunctionDecl, semantic: SemanticResult) -> str:
    rtype = _c_type_base(semantic.function_return_types.get(fn.name, "int"))
    params: list[str] = []
    ptypes = semantic.function_param_types.get(fn.name, ["int"] * len(fn.params))
    for name, ptype in zip(fn.params, ptypes):
        params.append(_decl_for_type(ptype, name))
    param_text = ", ".join(params) if params else "void"
    return f"{rtype} {fn.name}({param_text})"


def _emit_function(state: CGenState, fn: FunctionDecl, semantic: SemanticResult) -> None:
    state.emit(_function_signature(fn, semantic) + " {")
    state.indent += 1
    for stmt in fn.body.statements:
        _emit_stmt(state, stmt, semantic)
    state.indent -= 1
    state.emit("}")


def _emit_stmt(state: CGenState, stmt: object, semantic: SemanticResult) -> None:
    if isinstance(stmt, VarDecl):
        if stmt.array_size is not None:
            state.emit(_decl_for_type(f"array<{stmt.type_name},{stmt.array_size}>", stmt.name) + ";")
            return
        if stmt.init is None:
            state.emit(_decl_for_type(stmt.type_name, stmt.name) + ";")
            return
        init = _emit_expr(stmt.init, semantic, state)
        state.emit(_decl_for_type(stmt.type_name, stmt.name) + f" = {init};")
        return

    if isinstance(stmt, Assign):
        target_expr = stmt.target or Identifier(name=stmt.name, line=stmt.line, column=stmt.column)
        target = _emit_expr(target_expr, semantic, state)
        value = _emit_expr(stmt.value, semantic, state)
        state.emit(f"{target} = {value};")
        return

    if isinstance(stmt, IfStmt):
        cond = _emit_expr(stmt.condition, semantic, state)
        state.emit(f"if ({cond}) {{")
        state.indent += 1
        for inner in stmt.then_block.statements:
            _emit_stmt(state, inner, semantic)
        state.indent -= 1
        if stmt.else_block is None:
            state.emit("}")
            return
        state.emit("} else {")
        state.indent += 1
        for inner in stmt.else_block.statements:
            _emit_stmt(state, inner, semantic)
        state.indent -= 1
        state.emit("}")
        return

    if isinstance(stmt, WhileStmt):
        cond = _emit_expr(stmt.condition, semantic, state)
        state.emit(f"while ({cond}) {{")
        state.indent += 1
        for inner in stmt.body.statements:
            _emit_stmt(state, inner, semantic)
        state.indent -= 1
        state.emit("}")
        return

    if isinstance(stmt, DoWhileStmt):
        state.emit("do {")
        state.indent += 1
        for inner in stmt.body.statements:
            _emit_stmt(state, inner, semantic)
        state.indent -= 1
        cond = _emit_expr(stmt.condition, semantic, state)
        state.emit(f"}} while ({cond});")
        return

    if isinstance(stmt, SwitchStmt):
        cond = _emit_expr(stmt.condition, semantic, state)
        state.emit(f"switch ({cond}) {{")
        state.indent += 1
        for case in stmt.cases:
            label = _emit_expr(case.value, semantic, state)
            state.emit(f"case {label}:")
            state.indent += 1
            for inner in case.block.statements:
                _emit_stmt(state, inner, semantic)
            state.indent -= 1
        if stmt.default_block is not None:
            state.emit("default:")
            state.indent += 1
            for inner in stmt.default_block.statements:
                _emit_stmt(state, inner, semantic)
            state.indent -= 1
        state.indent -= 1
        state.emit("}")
        return

    if isinstance(stmt, ForStmt):
        init = _stmt_inline(stmt.init, semantic, state)
        cond = _emit_expr(stmt.condition, semantic, state) if stmt.condition is not None else ""
        post = _stmt_inline(stmt.post, semantic, state)
        state.emit(f"for ({init}; {cond}; {post}) {{")
        state.indent += 1
        for inner in stmt.body.statements:
            _emit_stmt(state, inner, semantic)
        state.indent -= 1
        state.emit("}")
        return

    if isinstance(stmt, BreakStmt):
        state.emit("break;")
        return

    if isinstance(stmt, ContinueStmt):
        state.emit("continue;")
        return

    if isinstance(stmt, PrintStmt):
        val = _emit_expr(stmt.value, semantic, state)
        t = semantic.expr_types.get(id(stmt.value), "int")
        if t == "text":
            state.emit(f"printf(\"%s\\n\", {val});")
        elif t == "float":
            state.emit(f"printf(\"%g\\n\", {val});")
        else:
            state.emit(f"printf(\"%d\\n\", {val});")
        return

    if isinstance(stmt, ReturnStmt):
        if stmt.value is None:
            state.emit("return;")
        else:
            state.emit(f"return {_emit_expr(stmt.value, semantic, state)};")
        return

    if isinstance(stmt, ExprStmt):
        state.emit(_emit_expr(stmt.expr, semantic, state) + ";")
        return

    if isinstance(stmt, Block):
        state.emit("{")
        state.indent += 1
        for inner in stmt.statements:
            _emit_stmt(state, inner, semantic)
        state.indent -= 1
        state.emit("}")


def _stmt_inline(stmt: object | None, semantic: SemanticResult, state: CGenState) -> str:
    if stmt is None:
        return ""
    if isinstance(stmt, VarDecl):
        if stmt.array_size is not None:
            return _decl_for_type(f"array<{stmt.type_name},{stmt.array_size}>", stmt.name)
        if stmt.init is None:
            return _decl_for_type(stmt.type_name, stmt.name)
        return _decl_for_type(stmt.type_name, stmt.name) + " = " + _emit_expr(stmt.init, semantic, state)
    if isinstance(stmt, Assign):
        target_expr = stmt.target or Identifier(name=stmt.name, line=stmt.line, column=stmt.column)
        return _emit_expr(target_expr, semantic, state) + " = " + _emit_expr(stmt.value, semantic, state)
    if isinstance(stmt, ExprStmt):
        return _emit_expr(stmt.expr, semantic, state)
    return ""


def _emit_expr(expr: Expr | None, semantic: SemanticResult, state: CGenState) -> str:
    if expr is None:
        return "0"
    if isinstance(expr, Identifier):
        return expr.name
    if isinstance(expr, Literal):
        if isinstance(expr.value, bool):
            return "1" if expr.value else "0"
        if isinstance(expr.value, float):
            text = f"{expr.value:g}"
            if "." not in text and "e" not in text and "E" not in text:
                text += ".0"
            return text
        if isinstance(expr.value, int):
            return str(expr.value)
        return _c_string_literal(expr.value)
    if isinstance(expr, Unary):
        return f"({expr.op}{_emit_expr(expr.operand, semantic, state)})"
    if isinstance(expr, Binary):
        left = _emit_expr(expr.left, semantic, state)
        right = _emit_expr(expr.right, semantic, state)
        return f"({left} {expr.op} {right})"
    if isinstance(expr, IndexAccess):
        return f"{_emit_expr(expr.base, semantic, state)}[{_emit_expr(expr.index, semantic, state)}]"
    if isinstance(expr, MemberAccess):
        return f"{_emit_expr(expr.base, semantic, state)}.{expr.member}"
    if isinstance(expr, Cast):
        ctype = _c_type_base(expr.type_name)
        return f"(({ctype})({_emit_expr(expr.expr, semantic, state)}))"
    if isinstance(expr, Call):
        if expr.callee in {"input", "bata"}:
            state.uses_input = True
            return "patakha_input_int()"
        if expr.callee == "max":
            a = _emit_expr(expr.args[0], semantic, state)
            b = _emit_expr(expr.args[1], semantic, state)
            return f"(({a}) > ({b}) ? ({a}) : ({b}))"
        if expr.callee == "len":
            arg = expr.args[0]
            at = semantic.expr_types.get(id(arg), "int")
            rendered = _emit_expr(arg, semantic, state)
            if at == "text":
                return f"((int)strlen({rendered}))"
            if _is_array(at):
                return f"((int)(sizeof({rendered}) / sizeof(({rendered})[0])))"
            return "0"
        args = ", ".join(_emit_expr(a, semantic, state) for a in expr.args)
        return f"{expr.callee}({args})"
    return "0"


def _c_type_base(type_name: str) -> str:
    if type_name == "int":
        return "int"
    if type_name == "float":
        return "double"
    if type_name == "bool":
        return "int"
    if type_name == "text":
        return "char*"
    if type_name == "void":
        return "void"
    if type_name.startswith("struct "):
        return type_name.split(" ", 1)[1]
    if type_name.startswith("class "):
        return type_name.split(" ", 1)[1]
    if _is_array(type_name):
        return _c_type_base(_array_elem(type_name))
    return type_name


def _decl_for_type(type_name: str, name: str) -> str:
    if _is_array(type_name):
        elem = _array_elem(type_name)
        size = _array_size(type_name) or 1
        return f"{_c_type_base(elem)} {name}[{size}]"
    return f"{_c_type_base(type_name)} {name}"


def _is_array(type_name: str) -> bool:
    return type_name.startswith("array<") and type_name.endswith(">")


def _array_elem(type_name: str) -> str:
    inner = type_name[len("array<") : -1]
    cut = inner.rfind(",")
    if cut == -1:
        return "int"
    return inner[:cut]


def _array_size(type_name: str) -> int | None:
    inner = type_name[len("array<") : -1]
    cut = inner.rfind(",")
    if cut == -1:
        return None
    tail = inner[cut + 1 :]
    return int(tail) if tail.isdigit() else None


def _c_string_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
