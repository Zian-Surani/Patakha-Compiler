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
    Unary,
    VarDecl,
    WhileStmt,
)


@dataclass
class StackState:
    lines: list[str]
    label_counter: int = 0
    control_stack: list[tuple[str, str]] | None = None

    def __post_init__(self) -> None:
        if self.control_stack is None:
            self.control_stack = []

    def emit(self, line: str) -> None:
        self.lines.append(line)

    def new_label(self, prefix: str) -> str:
        name = f"{prefix}_{self.label_counter}"
        self.label_counter += 1
        return name


def generate_stack_code(program: Program) -> str:
    state = StackState(lines=[])

    for fn in program.functions:
        _emit_function(state, fn)
    _emit_main(state, program)

    return "\n".join(state.lines) + "\n"


def _emit_function(state: StackState, fn: FunctionDecl) -> None:
    state.emit(f"FUNC {fn.name} {len(fn.params)}")
    for p in fn.params:
        state.emit(f"PARAM {p}")
    for stmt in fn.body.statements:
        _emit_stmt(state, stmt)
    state.emit("PUSH_INT 0")
    state.emit("RET")
    state.emit("END")


def _emit_main(state: StackState, program: Program) -> None:
    state.emit("FUNC __main__ 0")
    for stmt in program.statements:
        _emit_stmt(state, stmt)
    state.emit("PUSH_INT 0")
    state.emit("RET")
    state.emit("END")


def _emit_stmt(state: StackState, stmt: object) -> None:
    if isinstance(stmt, VarDecl):
        state.emit(f"DECL {stmt.name}")
        if stmt.init is not None:
            _emit_expr(state, stmt.init)
            state.emit(f"STORE {stmt.name}")
        return

    if isinstance(stmt, Assign):
        _emit_expr(state, stmt.value)
        target = stmt.target or Identifier(name=stmt.name, line=stmt.line, column=stmt.column)
        if isinstance(target, Identifier):
            state.emit(f"STORE {target.name}")
        else:
            state.emit(f"STOREX {_target_text(target)}")
        return

    if isinstance(stmt, PrintStmt):
        _emit_expr(state, stmt.value)
        state.emit("PRINT")
        return

    if isinstance(stmt, ExprStmt):
        _emit_expr(state, stmt.expr)
        state.emit("POP")
        return

    if isinstance(stmt, ReturnStmt):
        if stmt.value is None:
            state.emit("PUSH_INT 0")
        else:
            _emit_expr(state, stmt.value)
        state.emit("RET")
        return

    if isinstance(stmt, IfStmt):
        else_label = state.new_label("ELSE")
        end_label = state.new_label("ENDIF")
        _emit_expr(state, stmt.condition)
        state.emit(f"JZ {else_label}")
        _emit_stmt(state, stmt.then_block)
        state.emit(f"JMP {end_label}")
        state.emit(f"LABEL {else_label}")
        if stmt.else_block is not None:
            _emit_stmt(state, stmt.else_block)
        state.emit(f"LABEL {end_label}")
        return

    if isinstance(stmt, WhileStmt):
        start = state.new_label("WHILE_START")
        end = state.new_label("WHILE_END")
        state.control_stack.append((end, start))
        state.emit(f"LABEL {start}")
        _emit_expr(state, stmt.condition)
        state.emit(f"JZ {end}")
        _emit_stmt(state, stmt.body)
        state.emit(f"JMP {start}")
        state.emit(f"LABEL {end}")
        state.control_stack.pop()
        return

    if isinstance(stmt, ForStmt):
        start = state.new_label("FOR_START")
        end = state.new_label("FOR_END")
        cont = state.new_label("FOR_CONT")
        if stmt.init is not None:
            _emit_stmt(state, stmt.init)
        state.control_stack.append((end, cont))
        state.emit(f"LABEL {start}")
        if stmt.condition is not None:
            _emit_expr(state, stmt.condition)
            state.emit(f"JZ {end}")
        _emit_stmt(state, stmt.body)
        state.emit(f"LABEL {cont}")
        if stmt.post is not None:
            _emit_stmt(state, stmt.post)
        state.emit(f"JMP {start}")
        state.emit(f"LABEL {end}")
        state.control_stack.pop()
        return

    if isinstance(stmt, DoWhileStmt):
        start = state.new_label("DO_START")
        end = state.new_label("DO_END")
        cont = state.new_label("DO_CONT")
        state.control_stack.append((end, cont))
        state.emit(f"LABEL {start}")
        _emit_stmt(state, stmt.body)
        state.emit(f"LABEL {cont}")
        _emit_expr(state, stmt.condition)
        state.emit(f"JNZ {start}")
        state.emit(f"LABEL {end}")
        state.control_stack.pop()
        return

    if isinstance(stmt, SwitchStmt):
        temp_var = f"__switch_tmp_{state.new_label('S')}"
        end = state.new_label("SWITCH_END")
        default_label = state.new_label("SWITCH_DEFAULT") if stmt.default_block is not None else end
        case_labels = [state.new_label("SWITCH_CASE") for _ in stmt.cases]

        state.emit(f"DECL {temp_var}")
        _emit_expr(state, stmt.condition)
        state.emit(f"STORE {temp_var}")
        for idx, case in enumerate(stmt.cases):
            state.emit(f"LOAD {temp_var}")
            _emit_expr(state, case.value)
            state.emit("EQ")
            state.emit(f"JNZ {case_labels[idx]}")
        state.emit(f"JMP {default_label}")

        state.control_stack.append((end, ""))
        for idx, case in enumerate(stmt.cases):
            state.emit(f"LABEL {case_labels[idx]}")
            for inner in case.block.statements:
                _emit_stmt(state, inner)
        if stmt.default_block is not None:
            state.emit(f"LABEL {default_label}")
            for inner in stmt.default_block.statements:
                _emit_stmt(state, inner)
        state.control_stack.pop()
        state.emit(f"LABEL {end}")
        return

    if isinstance(stmt, BreakStmt):
        if state.control_stack:
            state.emit(f"JMP {state.control_stack[-1][0]}")
        else:
            state.emit("TRAP break_outside_loop")
        return

    if isinstance(stmt, ContinueStmt):
        target = _find_continue_target(state.control_stack)
        if target is not None:
            state.emit(f"JMP {target}")
        else:
            state.emit("TRAP continue_outside_loop")
        return

    if isinstance(stmt, Block):
        for inner in stmt.statements:
            _emit_stmt(state, inner)


def _emit_expr(state: StackState, expr: Expr) -> None:
    if isinstance(expr, Literal):
        if isinstance(expr.value, bool):
            state.emit("PUSH_INT 1" if expr.value else "PUSH_INT 0")
        elif isinstance(expr.value, float):
            state.emit(f"PUSH_FLOAT {expr.value:g}")
        elif isinstance(expr.value, int):
            state.emit(f"PUSH_INT {expr.value}")
        else:
            state.emit(f"PUSH_STR {expr.value!r}")
        return

    if isinstance(expr, Identifier):
        state.emit(f"LOAD {expr.name}")
        return

    if isinstance(expr, Unary):
        _emit_expr(state, expr.operand)
        if expr.op == "-":
            state.emit("NEG")
        elif expr.op == "!":
            state.emit("NOT")
        return

    if isinstance(expr, Binary):
        _emit_expr(state, expr.left)
        _emit_expr(state, expr.right)
        op = {
            "+": "ADD",
            "-": "SUB",
            "*": "MUL",
            "/": "DIV",
            "%": "MOD",
            "<": "LT",
            "<=": "LE",
            ">": "GT",
            ">=": "GE",
            "==": "EQ",
            "!=": "NE",
            "&&": "AND",
            "||": "OR",
        }.get(expr.op, "NOP")
        state.emit(op)
        return

    if isinstance(expr, Call):
        for arg in expr.args:
            _emit_expr(state, arg)
        if expr.callee in {"input", "bata"}:
            state.emit("INPUT")
        elif expr.callee == "max":
            state.emit("MAX")
        elif expr.callee == "len":
            state.emit("LEN")
        else:
            state.emit(f"CALL {expr.callee} {len(expr.args)}")
        return

    if isinstance(expr, IndexAccess):
        _emit_expr(state, expr.base)
        _emit_expr(state, expr.index)
        state.emit("GETINDEX")
        return

    if isinstance(expr, MemberAccess):
        _emit_expr(state, expr.base)
        state.emit(f"GETFIELD {expr.member}")
        return

    if isinstance(expr, Cast):
        _emit_expr(state, expr.expr)
        if expr.type_name == "int":
            state.emit("CAST_INT")
        elif expr.type_name == "float":
            state.emit("CAST_FLOAT")
        elif expr.type_name == "bool":
            state.emit("CAST_BOOL")
        return


def _target_text(expr: Expr) -> str:
    if isinstance(expr, Identifier):
        return expr.name
    if isinstance(expr, IndexAccess):
        return f"{_target_text(expr.base)}[?]"
    if isinstance(expr, MemberAccess):
        return f"{_target_text(expr.base)}.{expr.member}"
    return "<?>"


def _find_continue_target(control_stack: list[tuple[str, str]] | None) -> str | None:
    if not control_stack:
        return None
    for _, cont in reversed(control_stack):
        if cont:
            return cont
    return None
