from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from patakha.ast_nodes import (
    Assign,
    Binary,
    Block,
    BreakStmt,
    Call,
    Cast,
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
from patakha.semantic import SemanticResult


class _ReturnSignal(Exception):
    def __init__(self, value: object) -> None:
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


@dataclass
class _Env:
    parent: _Env | None
    values: dict[str, object]

    def __init__(self, parent: _Env | None = None) -> None:
        self.parent = parent
        self.values = {}

    def define(self, name: str, value: object) -> None:
        self.values[name] = value

    def get(self, name: str) -> object:
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise NameError(name)

    def assign(self, name: str, value: object) -> None:
        if name in self.values:
            self.values[name] = value
            return
        if self.parent is not None:
            self.parent.assign(name, value)
            return
        raise NameError(name)


class Interpreter:
    def __init__(
        self,
        program: Program,
        semantic: SemanticResult,
        input_fn: Callable[[], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.program = program
        self.semantic = semantic
        self.input_fn = input_fn or input
        self.output_fn = output_fn or print
        self.functions: dict[str, FunctionDecl] = {fn.name: fn for fn in program.functions}
        self.global_env = _Env()

    def run(self) -> object:
        try:
            self._exec_block(self.program.statements, self.global_env)
        except _ReturnSignal as ret:
            return ret.value
        return 0

    def _exec_block(self, statements: list[object], env: _Env) -> None:
        for stmt in statements:
            self._exec_stmt(stmt, env)

    def _exec_stmt(self, stmt: object, env: _Env) -> None:
        if isinstance(stmt, VarDecl):
            value = self._default_value(stmt.type_name, stmt.array_size)
            if stmt.init is not None:
                value = self._eval_expr(stmt.init, env)
            env.define(stmt.name, value)
            return

        if isinstance(stmt, Assign):
            target = stmt.target or Identifier(name=stmt.name, line=stmt.line, column=stmt.column)
            value = self._eval_expr(stmt.value, env)
            self._assign_target(target, value, env)
            return

        if isinstance(stmt, PrintStmt):
            value = self._eval_expr(stmt.value, env)
            if isinstance(value, bool):
                self.output_fn("1" if value else "0")
            else:
                self.output_fn(str(value))
            return

        if isinstance(stmt, ExprStmt):
            self._eval_expr(stmt.expr, env)
            return

        if isinstance(stmt, ReturnStmt):
            value = self._eval_expr(stmt.value, env) if stmt.value is not None else 0
            raise _ReturnSignal(value)

        if isinstance(stmt, IfStmt):
            if self._truthy(self._eval_expr(stmt.condition, env)):
                self._exec_stmt(stmt.then_block, _Env(env))
            elif stmt.else_block is not None:
                self._exec_stmt(stmt.else_block, _Env(env))
            return

        if isinstance(stmt, WhileStmt):
            while self._truthy(self._eval_expr(stmt.condition, env)):
                try:
                    self._exec_stmt(stmt.body, _Env(env))
                except _ContinueSignal:
                    continue
                except _BreakSignal:
                    break
            return

        if isinstance(stmt, ForStmt):
            loop_env = _Env(env)
            if stmt.init is not None:
                self._exec_stmt(stmt.init, loop_env)
            while True:
                if stmt.condition is not None and not self._truthy(self._eval_expr(stmt.condition, loop_env)):
                    break
                try:
                    self._exec_stmt(stmt.body, _Env(loop_env))
                except _ContinueSignal:
                    pass
                except _BreakSignal:
                    break
                if stmt.post is not None:
                    self._exec_stmt(stmt.post, loop_env)
            return

        if isinstance(stmt, DoWhileStmt):
            while True:
                try:
                    self._exec_stmt(stmt.body, _Env(env))
                except _ContinueSignal:
                    pass
                except _BreakSignal:
                    break
                if not self._truthy(self._eval_expr(stmt.condition, env)):
                    break
            return

        if isinstance(stmt, SwitchStmt):
            cond = self._eval_expr(stmt.condition, env)
            matched = False
            try:
                for case in stmt.cases:
                    if matched or self._eval_expr(case.value, env) == cond:
                        matched = True
                        self._exec_stmt(case.block, _Env(env))
                if not matched and stmt.default_block is not None:
                    self._exec_stmt(stmt.default_block, _Env(env))
            except _BreakSignal:
                pass
            return

        if isinstance(stmt, BreakStmt):
            raise _BreakSignal()
        if isinstance(stmt, ContinueStmt):
            raise _ContinueSignal()

        if isinstance(stmt, Block):
            self._exec_block(stmt.statements, _Env(env))
            return

    def _eval_expr(self, expr: Expr | None, env: _Env) -> object:
        if expr is None:
            return 0
        if isinstance(expr, Literal):
            return expr.value
        if isinstance(expr, Identifier):
            return env.get(expr.name)
        if isinstance(expr, Unary):
            v = self._eval_expr(expr.operand, env)
            if expr.op == "-":
                return -float(v) if isinstance(v, float) else -int(v)
            if expr.op == "!":
                return not self._truthy(v)
            return v
        if isinstance(expr, Binary):
            left = self._eval_expr(expr.left, env)
            right = self._eval_expr(expr.right, env)
            return self._eval_binary(expr.op, left, right)
        if isinstance(expr, IndexAccess):
            base = self._eval_expr(expr.base, env)
            idx = int(self._eval_expr(expr.index, env))
            return base[idx]
        if isinstance(expr, MemberAccess):
            base = self._eval_expr(expr.base, env)
            if not isinstance(base, dict):
                raise TypeError("Member access on non-object value")
            return base.get(expr.member, 0)
        if isinstance(expr, Cast):
            val = self._eval_expr(expr.expr, env)
            if expr.type_name == "int":
                return int(val)
            if expr.type_name == "float":
                return float(val)
            if expr.type_name == "bool":
                return self._truthy(val)
            if expr.type_name == "text":
                return str(val)
            return val
        if isinstance(expr, Call):
            return self._call(expr, env)
        return 0

    def _call(self, expr: Call, env: _Env) -> object:
        args = [self._eval_expr(a, env) for a in expr.args]

        if expr.callee in {"input", "bata"}:
            raw = self.input_fn().strip()
            if raw == "":
                return 0
            try:
                if "." in raw:
                    return float(raw)
                return int(raw)
            except ValueError:
                return 0
        if expr.callee == "max":
            return max(args[0], args[1])
        if expr.callee == "len":
            return len(args[0])

        fn = self.functions.get(expr.callee)
        if fn is None:
            raise NameError(expr.callee)

        call_env = _Env(self.global_env)
        param_names = fn.params
        for name, value in zip(param_names, args):
            call_env.define(name, value)
        try:
            self._exec_block(fn.body.statements, call_env)
        except _ReturnSignal as ret:
            return ret.value
        return 0

    def _assign_target(self, target: Expr, value: object, env: _Env) -> None:
        if isinstance(target, Identifier):
            env.assign(target.name, value)
            return
        if isinstance(target, IndexAccess):
            base = self._eval_expr(target.base, env)
            idx = int(self._eval_expr(target.index, env))
            base[idx] = value
            return
        if isinstance(target, MemberAccess):
            base = self._eval_expr(target.base, env)
            if not isinstance(base, dict):
                raise TypeError("Member assignment on non-object value")
            base[target.member] = value
            return
        raise TypeError("Invalid assignment target")

    def _default_value(self, type_name: str, array_size: int | None) -> object:
        if array_size is not None:
            return [self._default_scalar(type_name) for _ in range(array_size)]
        return self._default_scalar(type_name)

    def _default_scalar(self, type_name: str) -> object:
        if type_name == "bhai" or type_name == "int":
            return 0
        if type_name in {"decimal", "float"}:
            return 0.0
        if type_name == "bool":
            return False
        if type_name == "text":
            return ""

        tname = type_name
        if type_name.startswith("struct ") or type_name.startswith("class "):
            tname = type_name.split(" ", 1)[1]
        fields = self.semantic.composite_fields.get(tname)
        if fields is None:
            return {}
        out: dict[str, object] = {}
        for fname, ftype in fields.items():
            out[fname] = self._default_scalar(ftype)
        return out

    def _eval_binary(self, op: str, left: object, right: object) -> object:
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return left / right
        if op == "%":
            return left % right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "&&":
            return self._truthy(left) and self._truthy(right)
        if op == "||":
            return self._truthy(left) or self._truthy(right)
        return 0

    def _truthy(self, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return len(value) > 0
        if value is None:
            return False
        return bool(value)


def run_program(
    program: Program,
    semantic: SemanticResult,
    input_fn: Callable[[], str] | None = None,
    output_fn: Callable[[str], None] | None = None,
) -> object:
    return Interpreter(program, semantic, input_fn=input_fn, output_fn=output_fn).run()
