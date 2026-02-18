from __future__ import annotations

from dataclasses import dataclass

from patakha.ast_nodes import (
    Assign,
    Binary,
    Block,
    Cast,
    Call,
    Expr,
    ExprStmt,
    FunctionDecl,
    Identifier,
    IfStmt,
    Literal,
    PrintStmt,
    Program,
    ReturnStmt,
    Unary,
    VarDecl,
    WhileStmt,
)


BINOP_TO_TAC = {
    "+": "add",
    "-": "sub",
    "*": "mul",
    "/": "div",
    "<": "lt",
    "<=": "le",
    ">": "gt",
    ">=": "ge",
    "==": "eq",
    "!=": "ne",
}


UNARY_TO_TAC = {
    "-": "neg",
}


@dataclass
class Instruction:
    op: str
    arg1: object | None = None
    arg2: object | None = None
    result: str | None = None

    def __str__(self) -> str:
        if self.op == "copy":
            return f"{self.result} = {self.arg1}"
        if self.op in {"add", "sub", "mul", "div", "lt", "le", "gt", "ge", "eq", "ne"}:
            symbol = {
                "add": "+",
                "sub": "-",
                "mul": "*",
                "div": "/",
                "lt": "<",
                "le": "<=",
                "gt": ">",
                "ge": ">=",
                "eq": "==",
                "ne": "!=",
            }[self.op]
            return f"{self.result} = {self.arg1} {symbol} {self.arg2}"
        if self.op == "neg":
            return f"{self.result} = -{self.arg1}"
        if self.op == "label":
            return f"{self.result}:"
        if self.op == "goto":
            return f"goto {self.result}"
        if self.op == "ifz":
            return f"ifz {self.arg1} goto {self.result}"
        if self.op == "ifnz":
            return f"ifnz {self.arg1} goto {self.result}"
        if self.op == "print":
            if self.arg2 == "string":
                return f"print_str({self.arg1})"
            return f"print_int({self.arg1})"
        if self.op == "param":
            return f"param {self.arg1}"
        if self.op == "call":
            args = int(self.arg2 or 0)
            if self.result:
                return f"{self.result} = call {self.arg1}, {args}"
            return f"call {self.arg1}, {args}"
        if self.op == "return":
            return f"return {self.arg1}"
        return f"{self.op} {self.arg1} {self.arg2} {self.result}"


@dataclass
class IRFunction:
    name: str
    params: list[str]
    instructions: list[Instruction]
    temp_vars: set[str]
    local_vars: set[str]


@dataclass
class IRResult:
    functions: list[IRFunction]


class IRGenerator:
    def __init__(self) -> None:
        self.instructions: list[Instruction] = []
        self.temp_counter = 0
        self.label_counter = 0
        self.temp_vars: set[str] = set()
        self.local_vars: set[str] = set()
        self.scope_stack: list[dict[str, str]] = []
        self.name_counter = 0
        self.used_internal_names: set[str] = set()

    def generate(self, program: Program) -> IRResult:
        functions: list[IRFunction] = []

        for func in program.functions:
            functions.append(self._emit_function(func.name, func.params, func.body.statements))

        functions.append(self._emit_function("__main__", [], program.statements))
        return IRResult(functions=functions)

    def _emit_function(
        self,
        name: str,
        params: list[str],
        statements: list[object],
    ) -> IRFunction:
        self.instructions = []
        self.temp_counter = 0
        self.label_counter = 0
        self.name_counter = 0
        self.temp_vars = set()
        self.local_vars = set()
        self.scope_stack = []
        self.used_internal_names = set()

        self._push_scope()
        remapped_params: list[str] = []
        for param in params:
            internal = self._declare_var(param)
            remapped_params.append(internal)

        for stmt in statements:
            self._emit_stmt(stmt)

        self._pop_scope()

        return IRFunction(
            name=name,
            params=remapped_params,
            instructions=list(self.instructions),
            temp_vars=set(self.temp_vars),
            local_vars=set(self.local_vars),
        )

    def _emit_stmt(self, stmt: object) -> None:
        if isinstance(stmt, VarDecl):
            internal_name = self._declare_var(stmt.name)
            if stmt.init is not None:
                rhs = self._emit_expr(stmt.init)
                self.instructions.append(Instruction(op="copy", arg1=rhs, result=internal_name))
            return

        if isinstance(stmt, Assign):
            rhs = self._emit_expr(stmt.value)
            self.instructions.append(
                Instruction(op="copy", arg1=rhs, result=self._resolve_var(stmt.name))
            )
            return

        if isinstance(stmt, PrintStmt):
            if isinstance(stmt.value, Literal) and isinstance(stmt.value.value, str):
                c_string = _c_string_literal(stmt.value.value)
                self.instructions.append(Instruction(op="print", arg1=c_string, arg2="string"))
            else:
                value_ref = self._emit_expr(stmt.value)
                self.instructions.append(Instruction(op="print", arg1=value_ref, arg2="int"))
            return

        if isinstance(stmt, ReturnStmt):
            value_ref = self._emit_expr(stmt.value)
            self.instructions.append(Instruction(op="return", arg1=value_ref))
            return

        if isinstance(stmt, ExprStmt):
            if isinstance(stmt.expr, Call):
                self._emit_call(stmt.expr, want_result=False)
            else:
                self._emit_expr(stmt.expr)
            return

        if isinstance(stmt, Block):
            self._push_scope()
            for inner in stmt.statements:
                self._emit_stmt(inner)
            self._pop_scope()
            return

        if isinstance(stmt, IfStmt):
            then_label = self._new_label()
            else_label = self._new_label()
            end_label = self._new_label() if stmt.else_block is not None else else_label
            self._emit_cond_jump(stmt.condition, true_label=then_label, false_label=else_label)
            self.instructions.append(Instruction(op="label", result=then_label))
            self._emit_stmt(stmt.then_block)
            if stmt.else_block is not None:
                self.instructions.append(Instruction(op="goto", result=end_label))
                self.instructions.append(Instruction(op="label", result=else_label))
                self._emit_stmt(stmt.else_block)
                self.instructions.append(Instruction(op="label", result=end_label))
            else:
                self.instructions.append(Instruction(op="label", result=else_label))
            return

        if isinstance(stmt, WhileStmt):
            loop_check = self._new_label()
            loop_body = self._new_label()
            loop_end = self._new_label()
            self.instructions.append(Instruction(op="label", result=loop_check))
            self._emit_cond_jump(stmt.condition, true_label=loop_body, false_label=loop_end)
            self.instructions.append(Instruction(op="label", result=loop_body))
            self._emit_stmt(stmt.body)
            self.instructions.append(Instruction(op="goto", result=loop_check))
            self.instructions.append(Instruction(op="label", result=loop_end))
            return

    def _emit_expr(self, expr: Expr, allow_short_circuit: bool = True) -> str:
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

        if isinstance(expr, Identifier):
            return self._resolve_var(expr.name)

        if isinstance(expr, Call):
            result = self._emit_call(expr, want_result=True)
            if result is None:
                raise RuntimeError("Call expression missing result.")
            return result

        if isinstance(expr, Cast):
            return self._emit_expr(expr.expr, allow_short_circuit=allow_short_circuit)

        if isinstance(expr, Unary):
            if expr.op == "!":
                if allow_short_circuit:
                    return self._emit_bool_value(expr)
                operand = self._emit_expr(expr.operand, allow_short_circuit=False)
                temp = self._new_temp()
                self.instructions.append(Instruction(op="eq", arg1=operand, arg2="0", result=temp))
                return temp
            operand = self._emit_expr(expr.operand)
            temp = self._new_temp()
            self.instructions.append(Instruction(op=UNARY_TO_TAC[expr.op], arg1=operand, result=temp))
            return temp

        if isinstance(expr, Binary):
            if expr.op in {"&&", "||"} and allow_short_circuit:
                return self._emit_bool_value(expr)
            left = self._emit_expr(expr.left)
            right = self._emit_expr(expr.right)
            temp = self._new_temp()
            self.instructions.append(
                Instruction(op=BINOP_TO_TAC[expr.op], arg1=left, arg2=right, result=temp)
            )
            return temp

        raise TypeError(f"Unsupported expression node: {type(expr)}")

    def _emit_call(self, call: Call, want_result: bool) -> str | None:
        args: list[str] = []
        for arg in call.args:
            args.append(self._emit_expr(arg))
        for arg in args:
            self.instructions.append(Instruction(op="param", arg1=arg))
        result = self._new_temp() if want_result else None
        self.instructions.append(
            Instruction(op="call", arg1=call.callee, arg2=len(args), result=result)
        )
        return result

    def _emit_bool_value(self, expr: Expr) -> str:
        result = self._new_temp()
        true_label = self._new_label()
        false_label = self._new_label()
        end_label = self._new_label()

        self.instructions.append(Instruction(op="copy", arg1="0", result=result))
        self._emit_cond_jump(expr, true_label=true_label, false_label=false_label)
        self.instructions.append(Instruction(op="label", result=true_label))
        self.instructions.append(Instruction(op="copy", arg1="1", result=result))
        self.instructions.append(Instruction(op="goto", result=end_label))
        self.instructions.append(Instruction(op="label", result=false_label))
        self.instructions.append(Instruction(op="label", result=end_label))
        return result

    def _emit_cond_jump(self, expr: Expr, true_label: str, false_label: str) -> None:
        if isinstance(expr, Literal) and isinstance(expr.value, bool):
            self.instructions.append(
                Instruction(op="goto", result=true_label if expr.value else false_label)
            )
            return

        if isinstance(expr, Unary) and expr.op == "!":
            self._emit_cond_jump(expr.operand, true_label=false_label, false_label=true_label)
            return

        if isinstance(expr, Binary) and expr.op == "&&":
            mid = self._new_label()
            self._emit_cond_jump(expr.left, true_label=mid, false_label=false_label)
            self.instructions.append(Instruction(op="label", result=mid))
            self._emit_cond_jump(expr.right, true_label=true_label, false_label=false_label)
            return

        if isinstance(expr, Binary) and expr.op == "||":
            mid = self._new_label()
            self._emit_cond_jump(expr.left, true_label=true_label, false_label=mid)
            self.instructions.append(Instruction(op="label", result=mid))
            self._emit_cond_jump(expr.right, true_label=true_label, false_label=false_label)
            return

        cond_ref = self._emit_expr(expr, allow_short_circuit=False)
        self.instructions.append(Instruction(op="ifnz", arg1=cond_ref, result=true_label))
        self.instructions.append(Instruction(op="goto", result=false_label))

    def _new_temp(self) -> str:
        name = f"_t{self.temp_counter}"
        self.temp_counter += 1
        self.temp_vars.add(name)
        return name

    def _new_label(self) -> str:
        name = f"L{self.label_counter}"
        self.label_counter += 1
        return name

    def _push_scope(self) -> None:
        self.scope_stack.append({})

    def _pop_scope(self) -> None:
        self.scope_stack.pop()

    def _declare_var(self, source_name: str) -> str:
        current = self.scope_stack[-1]
        if source_name in current:
            return current[source_name]
        internal = source_name
        if internal in self.used_internal_names:
            internal = f"{source_name}__{self.name_counter}"
            self.name_counter += 1
            while internal in self.used_internal_names:
                internal = f"{source_name}__{self.name_counter}"
                self.name_counter += 1
        current[source_name] = internal
        self.local_vars.add(internal)
        self.used_internal_names.add(internal)
        return internal

    def _resolve_var(self, source_name: str) -> str:
        for scope in reversed(self.scope_stack):
            if source_name in scope:
                return scope[source_name]
        return source_name


def _c_string_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'
