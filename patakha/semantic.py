from __future__ import annotations

import difflib
from dataclasses import dataclass

from patakha.ast_nodes import (
    Assign,
    Binary,
    Block,
    BreakStmt,
    CaseClause,
    Call,
    ContinueStmt,
    Cast,
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
    Param,
    PrintStmt,
    Program,
    ReturnStmt,
    SwitchStmt,
    TypeDecl,
    Unary,
    VarDecl,
    WhileStmt,
)
from patakha.diagnostics import PatakhaError, PatakhaWarning


PRIMITIVES = {"int", "float", "bool", "text", "void"}
BUILTINS = {"len", "max", "bata", "input"}
KEYWORD_HINTS = {
    "agar",
    "warna",
    "tabtak",
    "jabtak",
    "kar",
    "switch",
    "case",
    "default",
    "tod",
    "jari",
    "nikal",
    "bol",
    "shuru",
    "bass",
}


@dataclass
class CompositeType:
    kind: str
    name: str
    fields: dict[str, str]


@dataclass
class FunctionSig:
    return_type: str
    params: list[tuple[str, str]]


@dataclass
class VarSymbol:
    type_name: str
    line: int
    column: int
    used: bool = False


@dataclass
class SemanticResult:
    function_signatures: dict[str, int]
    function_return_types: dict[str, str]
    function_param_types: dict[str, list[str]]
    locals_by_function: dict[str, set[str]]
    scope_snapshots: list[tuple[str, dict[str, str]]]
    warnings: list[PatakhaWarning]
    expr_types: dict[int, str]
    composite_kinds: dict[str, str]
    composite_fields: dict[str, dict[str, str]]


class SemanticAnalyzer:
    def __init__(self) -> None:
        self.composite_types: dict[str, CompositeType] = {}
        self.function_sigs: dict[str, FunctionSig] = {}
        self.function_signatures: dict[str, int] = {}
        self.function_return_types: dict[str, str] = {}
        self.function_param_types: dict[str, list[str]] = {}

        self.scopes: list[dict[str, VarSymbol]] = []
        self.scope_names: list[str] = []
        self.scope_counter = 0
        self.scope_snapshots: list[tuple[str, dict[str, str]]] = []
        self.locals_by_function: dict[str, set[str]] = {"__main__": set()}

        self.current_function = "__main__"
        self.current_return_type = "int"
        self.loop_depth = 0
        self.switch_depth = 0

        self.warnings: list[PatakhaWarning] = []
        self.expr_types: dict[int, str] = {}

    def analyze(self, program: Program) -> SemanticResult:
        self._collect_composite_names(program.type_decls)
        self._collect_composite_fields(program.type_decls)
        self._collect_function_signatures(program.functions)

        for fn in program.functions:
            self._analyze_function(fn)

        self.current_function = "__main__"
        self.current_return_type = "int"
        self._push_scope("main")
        self._visit_block(Block(statements=program.statements, line=1, column=1), create_scope=False)
        self._pop_scope()

        return SemanticResult(
            function_signatures=dict(self.function_signatures),
            function_return_types=dict(self.function_return_types),
            function_param_types={k: list(v) for k, v in self.function_param_types.items()},
            locals_by_function={k: set(v) for k, v in self.locals_by_function.items()},
            scope_snapshots=list(self.scope_snapshots),
            warnings=list(self.warnings),
            expr_types=dict(self.expr_types),
            composite_kinds={k: v.kind for k, v in self.composite_types.items()},
            composite_fields={k: dict(v.fields) for k, v in self.composite_types.items()},
        )

    def _collect_composite_names(self, decls: list[TypeDecl]) -> None:
        for decl in decls:
            if decl.name in PRIMITIVES or decl.name in BUILTINS:
                raise PatakhaError(
                    code="redeclared_variable",
                    technical=f"Type `{decl.name}` uses reserved name.",
                    line=decl.line,
                    column=decl.column,
                )
            if decl.name in self.composite_types:
                raise PatakhaError(
                    code="redeclared_variable",
                    technical=f"Type `{decl.name}` already declared.",
                    line=decl.line,
                    column=decl.column,
                )
            self.composite_types[decl.name] = CompositeType(
                kind=decl.kind,
                name=decl.name,
                fields={},
            )

    def _collect_composite_fields(self, decls: list[TypeDecl]) -> None:
        for decl in decls:
            c = self.composite_types[decl.name]
            for field in decl.fields:
                if field.name in c.fields:
                    raise PatakhaError(
                        code="redeclared_variable",
                        technical=f"Field `{field.name}` duplicated in `{decl.name}`.",
                        line=field.line,
                        column=field.column,
                    )
                field_type = self._resolve_type_name(
                    field.type_name,
                    allow_void=False,
                    line=field.line,
                    column=field.column,
                )
                if field.array_size is not None:
                    if field.array_size <= 0:
                        raise PatakhaError(
                            code="type_mismatch",
                            technical="Array size must be positive.",
                            line=field.line,
                            column=field.column,
                        )
                    field_type = _array_of(field_type, field.array_size)
                c.fields[field.name] = field_type

    def _collect_function_signatures(self, functions: list[FunctionDecl]) -> None:
        for fn in functions:
            if fn.name in BUILTINS:
                raise PatakhaError(
                    code="redeclared_variable",
                    technical=f"Function `{fn.name}` conflicts with builtin name.",
                    line=fn.line,
                    column=fn.column,
                )
            if fn.name in self.composite_types:
                raise PatakhaError(
                    code="redeclared_variable",
                    technical=f"Function `{fn.name}` conflicts with type name.",
                    line=fn.line,
                    column=fn.column,
                )
            if fn.name in self.function_sigs:
                raise PatakhaError(
                    code="redeclared_variable",
                    technical=f"Function `{fn.name}` already declared.",
                    line=fn.line,
                    column=fn.column,
                )

            typed_params = fn.typed_params or [
                Param(type_name="int", name=name, line=fn.line, column=fn.column)
                for name in fn.params
            ]
            params: list[tuple[str, str]] = []
            seen_param: set[str] = set()
            for p in typed_params:
                if p.name in seen_param:
                    raise PatakhaError(
                        code="invalid_params",
                        technical=f"Duplicate parameter `{p.name}` in `{fn.name}`.",
                        line=p.line,
                        column=p.column,
                    )
                seen_param.add(p.name)
                ptype = self._resolve_type_name(
                    p.type_name,
                    allow_void=False,
                    line=p.line,
                    column=p.column,
                )
                params.append((p.name, ptype))

            rtype = self._resolve_type_name(
                fn.return_type,
                allow_void=True,
                line=fn.line,
                column=fn.column,
            )
            sig = FunctionSig(return_type=rtype, params=params)
            self.function_sigs[fn.name] = sig
            self.function_signatures[fn.name] = len(params)
            self.function_return_types[fn.name] = rtype
            self.function_param_types[fn.name] = [ptype for _, ptype in params]
            self.locals_by_function[fn.name] = {name for name, _ in params}

    def _analyze_function(self, fn: FunctionDecl) -> None:
        sig = self.function_sigs[fn.name]
        prev_function = self.current_function
        prev_return = self.current_return_type
        self.current_function = fn.name
        self.current_return_type = sig.return_type

        self._push_scope(f"fn {fn.name}")
        for name, ptype in sig.params:
            self._declare_var(name, ptype, fn.line, fn.column)
        always_returns = self._visit_block(fn.body, create_scope=False)
        if sig.return_type != "void" and not always_returns:
            self._warn(
                code="missing_return",
                message=f"Function `{fn.name}` may exit without `nikal` value.",
                line=fn.line,
                column=fn.column,
            )
        self._pop_scope()

        self.current_function = prev_function
        self.current_return_type = prev_return

    def _visit_block(self, block: Block, create_scope: bool) -> bool:
        if create_scope:
            self._push_scope("block")
        terminated = False
        for stmt in block.statements:
            if terminated:
                self._warn(
                    code="unreachable_code",
                    message="Unreachable statement after control-flow exit.",
                    line=getattr(stmt, "line", block.line),
                    column=getattr(stmt, "column", block.column),
                )
                continue
            terminated = self._visit_stmt(stmt)
        if create_scope:
            self._pop_scope()
        return terminated

    def _visit_stmt(self, stmt: object) -> bool:
        if isinstance(stmt, VarDecl):
            self._visit_var_decl(stmt)
            return False
        if isinstance(stmt, Assign):
            self._visit_assign(stmt)
            return False
        if isinstance(stmt, IfStmt):
            return self._visit_if(stmt)
        if isinstance(stmt, WhileStmt):
            self._visit_while(stmt)
            return False
        if isinstance(stmt, ForStmt):
            self._visit_for(stmt)
            return False
        if isinstance(stmt, DoWhileStmt):
            self._visit_do_while(stmt)
            return False
        if isinstance(stmt, SwitchStmt):
            self._visit_switch(stmt)
            return False
        if isinstance(stmt, BreakStmt):
            if self.loop_depth <= 0 and self.switch_depth <= 0:
                raise PatakhaError(
                    code="break_outside_loop",
                    technical="`tod` used outside loop/switch.",
                    line=stmt.line,
                    column=stmt.column,
                )
            return True
        if isinstance(stmt, ContinueStmt):
            if self.loop_depth <= 0:
                raise PatakhaError(
                    code="continue_outside_loop",
                    technical="`jari` used outside loop.",
                    line=stmt.line,
                    column=stmt.column,
                )
            return True
        if isinstance(stmt, PrintStmt):
            t = self._infer_expr_type(stmt.value)
            if t not in {"int", "float", "bool", "text"}:
                raise PatakhaError(
                    code="type_mismatch",
                    technical=f"`bol` supports int/float/bool/text, got {t}.",
                    line=stmt.line,
                    column=stmt.column,
                )
            return False
        if isinstance(stmt, ReturnStmt):
            self._visit_return(stmt)
            return True
        if isinstance(stmt, ExprStmt):
            self._infer_expr_type(stmt.expr)
            return False
        if isinstance(stmt, Block):
            return self._visit_block(stmt, create_scope=True)
        return False

    def _visit_var_decl(self, stmt: VarDecl) -> None:
        if stmt.name in BUILTINS or stmt.name in self.function_sigs or stmt.name in self.composite_types:
            raise PatakhaError(
                code="redeclared_variable",
                technical=f"Variable `{stmt.name}` conflicts with reserved/function/type name.",
                line=stmt.line,
                column=stmt.column,
            )
        declared = self._resolve_type_name(
            stmt.type_name,
            allow_void=False,
            line=stmt.line,
            column=stmt.column,
        )
        if stmt.array_size is not None:
            if stmt.array_size <= 0:
                raise PatakhaError(
                    code="type_mismatch",
                    technical="Array size must be positive.",
                    line=stmt.line,
                    column=stmt.column,
                )
            declared = _array_of(declared, stmt.array_size)
            if stmt.init is not None:
                raise PatakhaError(
                    code="array_init_not_supported",
                    technical="Array declaration with initializer is not supported yet.",
                    line=stmt.line,
                    column=stmt.column,
                )

        self._declare_var(stmt.name, declared, stmt.line, stmt.column)
        if stmt.init is not None:
            rhs = self._infer_expr_type(stmt.init)
            if not _is_assignable(declared, rhs):
                raise PatakhaError(
                    code="type_mismatch",
                    technical=f"Cannot initialize `{stmt.name}` ({declared}) with {rhs}.",
                    line=stmt.line,
                    column=stmt.column,
                )

    def _visit_assign(self, stmt: Assign) -> None:
        target_expr: Expr
        if stmt.target is not None:
            target_expr = stmt.target
        else:
            target_expr = Identifier(name=stmt.name, line=stmt.line, column=stmt.column)
        lhs = self._infer_lvalue_type(target_expr)
        rhs = self._infer_expr_type(stmt.value)
        if not _is_assignable(lhs, rhs):
            raise PatakhaError(
                code="type_mismatch",
                technical=f"Cannot assign {rhs} to {lhs}.",
                line=stmt.line,
                column=stmt.column,
            )

    def _visit_if(self, stmt: IfStmt) -> bool:
        self._check_condition(stmt.condition, stmt.line, stmt.column)
        then_returns = self._visit_block(stmt.then_block, create_scope=True)
        else_returns = False
        if stmt.else_block is not None:
            else_returns = self._visit_block(stmt.else_block, create_scope=True)
        return stmt.else_block is not None and then_returns and else_returns

    def _visit_while(self, stmt: WhileStmt) -> None:
        self._check_condition(stmt.condition, stmt.line, stmt.column)
        self.loop_depth += 1
        self._visit_block(stmt.body, create_scope=True)
        self.loop_depth -= 1

    def _visit_for(self, stmt: ForStmt) -> None:
        self._push_scope("for")
        if stmt.init is not None:
            self._visit_stmt(stmt.init)
        if stmt.condition is not None:
            self._check_condition(stmt.condition, stmt.line, stmt.column)
        self.loop_depth += 1
        self._visit_block(stmt.body, create_scope=True)
        self.loop_depth -= 1
        if stmt.post is not None:
            self._visit_stmt(stmt.post)
        self._pop_scope()

    def _visit_do_while(self, stmt: DoWhileStmt) -> None:
        self.loop_depth += 1
        self._visit_block(stmt.body, create_scope=True)
        self.loop_depth -= 1
        self._check_condition(stmt.condition, stmt.line, stmt.column)

    def _visit_switch(self, stmt: SwitchStmt) -> None:
        cond_type = self._infer_expr_type(stmt.condition)
        if cond_type not in {"int", "bool"}:
            raise PatakhaError(
                code="invalid_condition",
                technical=f"Switch condition should be int/bool, got {cond_type}.",
                line=stmt.line,
                column=stmt.column,
            )

        seen_case_values: set[int] = set()
        self.switch_depth += 1
        try:
            for case in stmt.cases:
                self._visit_case(case, cond_type, seen_case_values)
            if stmt.default_block is not None:
                self._visit_block(stmt.default_block, create_scope=True)
        finally:
            self.switch_depth -= 1

    def _visit_case(self, case: CaseClause, cond_type: str, seen_case_values: set[int]) -> None:
        case_type = self._infer_expr_type(case.value)
        if case_type not in {"int", "bool"}:
            raise PatakhaError(
                code="invalid_case_label",
                technical=f"Case label should be int/bool, got {case_type}.",
                line=case.line,
                column=case.column,
            )
        if not (_is_assignable(cond_type, case_type) or _is_assignable(case_type, cond_type)):
            raise PatakhaError(
                code="type_mismatch",
                technical=f"Case label type {case_type} mismatches switch type {cond_type}.",
                line=case.line,
                column=case.column,
            )
        const_value = self._eval_constant(case.value)
        if const_value is None:
            raise PatakhaError(
                code="invalid_case_label",
                technical="Case label must be compile-time constant int/bool expression.",
                line=case.line,
                column=case.column,
            )
        key = int(bool(const_value)) if isinstance(const_value, bool) else int(const_value)
        if key in seen_case_values:
            raise PatakhaError(
                code="duplicate_case",
                technical=f"Duplicate case label value `{key}` in switch.",
                line=case.line,
                column=case.column,
            )
        seen_case_values.add(key)
        self._visit_block(case.block, create_scope=True)

    def _visit_return(self, stmt: ReturnStmt) -> None:
        expected = self.current_return_type
        if expected == "void":
            if stmt.value is not None:
                raise PatakhaError(
                    code="return_type",
                    technical="Khali function cannot return a value.",
                    line=stmt.line,
                    column=stmt.column,
                )
            return
        if stmt.value is None:
            raise PatakhaError(
                code="return_type",
                technical=f"Function expects return type {expected}.",
                line=stmt.line,
                column=stmt.column,
            )
        actual = self._infer_expr_type(stmt.value)
        if not _is_assignable(expected, actual):
            raise PatakhaError(
                code="return_type",
                technical=f"Return type mismatch: expected {expected}, got {actual}.",
                line=stmt.line,
                column=stmt.column,
            )

    def _check_condition(self, expr: Expr, line: int, column: int) -> None:
        t = self._infer_expr_type(expr)
        if t not in {"int", "float", "bool"}:
            raise PatakhaError(
                code="invalid_condition",
                technical=f"Condition should be int/float/bool, got {t}.",
                line=line,
                column=column,
            )
        const_value = self._eval_constant(expr)
        if const_value is not None:
            self._warn(
                code="constant_condition",
                message="Condition is constant; branch/loop may be redundant.",
                line=line,
                column=column,
            )

    def _infer_lvalue_type(self, expr: Expr) -> str:
        if isinstance(expr, Identifier):
            sym = self._lookup(expr.name, expr.line, expr.column)
            return sym.type_name
        if isinstance(expr, IndexAccess):
            base = self._infer_expr_type(expr.base)
            idx = self._infer_expr_type(expr.index)
            if idx not in {"int", "bool"}:
                raise PatakhaError(
                    code="type_mismatch",
                    technical="Array index should be int/bool.",
                    line=expr.line,
                    column=expr.column,
                )
            if _is_array(base):
                return _array_elem(base)
            raise PatakhaError(
                code="invalid_lvalue",
                technical="Index assignment requires array target.",
                line=expr.line,
                column=expr.column,
            )
        if isinstance(expr, MemberAccess):
            base = self._infer_expr_type(expr.base)
            tname = _composite_name(base)
            if tname is None or tname not in self.composite_types:
                raise PatakhaError(
                    code="invalid_lvalue",
                    technical="Member assignment requires kaksha/struct target.",
                    line=expr.line,
                    column=expr.column,
                )
            c = self.composite_types[tname]
            if expr.member not in c.fields:
                raise PatakhaError(
                    code="undeclared_variable",
                    technical=f"Type `{tname}` has no field `{expr.member}`.",
                    line=expr.line,
                    column=expr.column,
                )
            return c.fields[expr.member]
        raise PatakhaError(
            code="invalid_lvalue",
            technical="Invalid assignment target.",
            line=getattr(expr, "line", 1),
            column=getattr(expr, "column", 1),
        )

    def _infer_expr_type(self, expr: Expr) -> str:
        if isinstance(expr, Literal):
            if isinstance(expr.value, bool):
                t = "bool"
            elif isinstance(expr.value, float):
                t = "float"
            elif isinstance(expr.value, int):
                t = "int"
            else:
                t = "text"
            self.expr_types[id(expr)] = t
            return t

        if isinstance(expr, Identifier):
            sym = self._lookup(expr.name, expr.line, expr.column)
            sym.used = True
            self.expr_types[id(expr)] = sym.type_name
            return sym.type_name

        if isinstance(expr, IndexAccess):
            base = self._infer_expr_type(expr.base)
            idx = self._infer_expr_type(expr.index)
            if idx not in {"int", "bool"}:
                raise PatakhaError(
                    code="type_mismatch",
                    technical="Array index should be int/bool.",
                    line=expr.line,
                    column=expr.column,
                )
            if _is_array(base):
                t = _array_elem(base)
                self.expr_types[id(expr)] = t
                return t
            if base == "text":
                self.expr_types[id(expr)] = "int"
                return "int"
            raise PatakhaError(
                code="type_mismatch",
                technical="Index access requires array/text expression.",
                line=expr.line,
                column=expr.column,
            )

        if isinstance(expr, MemberAccess):
            base = self._infer_expr_type(expr.base)
            tname = _composite_name(base)
            if tname is None or tname not in self.composite_types:
                raise PatakhaError(
                    code="type_mismatch",
                    technical="Member access requires kaksha/struct expression.",
                    line=expr.line,
                    column=expr.column,
                )
            c = self.composite_types[tname]
            if expr.member not in c.fields:
                raise PatakhaError(
                    code="undeclared_variable",
                    technical=f"Type `{tname}` has no field `{expr.member}`.",
                    line=expr.line,
                    column=expr.column,
                )
            t = c.fields[expr.member]
            self.expr_types[id(expr)] = t
            return t

        if isinstance(expr, Call):
            t = self._infer_call_type(expr)
            self.expr_types[id(expr)] = t
            return t

        if isinstance(expr, Unary):
            op_t = self._infer_expr_type(expr.operand)
            if expr.op == "-":
                if not _is_numeric(op_t):
                    raise PatakhaError(
                        code="type_mismatch",
                        technical="Unary `-` expects numeric operand.",
                        line=expr.line,
                        column=expr.column,
                    )
                self.expr_types[id(expr)] = op_t
                return op_t
            if expr.op == "!":
                if op_t not in {"int", "float", "bool"}:
                    raise PatakhaError(
                        code="type_mismatch",
                        technical="Unary `!` expects int/float/bool operand.",
                        line=expr.line,
                        column=expr.column,
                    )
                self.expr_types[id(expr)] = "bool"
                return "bool"

        if isinstance(expr, Cast):
            src_t = self._infer_expr_type(expr.expr)
            dst_t = self._resolve_type_name(
                expr.type_name,
                allow_void=False,
                line=expr.line,
                column=expr.column,
            )
            if not _is_castable(src_t, dst_t):
                raise PatakhaError(
                    code="type_mismatch",
                    technical=f"Cannot cast {src_t} to {dst_t}.",
                    line=expr.line,
                    column=expr.column,
                )
            self.expr_types[id(expr)] = dst_t
            return dst_t

        if isinstance(expr, Binary):
            left = self._infer_expr_type(expr.left)
            right = self._infer_expr_type(expr.right)
            op = expr.op

            if op == "+" and left == right == "text":
                self.expr_types[id(expr)] = "text"
                return "text"
            if op in {"+", "-", "*", "/", "%"}:
                if op == "%" and (left != "int" or right != "int"):
                    raise PatakhaError(
                        code="type_mismatch",
                        technical="Operator `%` expects int operands.",
                        line=expr.line,
                        column=expr.column,
                    )
                if _is_numeric(left) and _is_numeric(right):
                    out_t = _numeric_result(left, right)
                    self.expr_types[id(expr)] = out_t
                    return out_t
                raise PatakhaError(
                    code="type_mismatch",
                    technical=f"Operator `{op}` expects numeric operands.",
                    line=expr.line,
                    column=expr.column,
                )
            if op in {"<", "<=", ">", ">="}:
                if _is_numeric(left) and _is_numeric(right):
                    self.expr_types[id(expr)] = "bool"
                    return "bool"
                raise PatakhaError(
                    code="type_mismatch",
                    technical=f"Operator `{op}` expects numeric operands.",
                    line=expr.line,
                    column=expr.column,
                )
            if op in {"==", "!="}:
                if _is_assignable(left, right) or _is_assignable(right, left):
                    self.expr_types[id(expr)] = "bool"
                    return "bool"
                raise PatakhaError(
                    code="type_mismatch",
                    technical=f"Cannot compare {left} with {right}.",
                    line=expr.line,
                    column=expr.column,
                )
            if op in {"&&", "||"}:
                if left in {"int", "float", "bool"} and right in {"int", "float", "bool"}:
                    self.expr_types[id(expr)] = "bool"
                    return "bool"
                raise PatakhaError(
                    code="type_mismatch",
                    technical=f"Operator `{op}` expects int/float/bool operands.",
                    line=expr.line,
                    column=expr.column,
                )

        raise PatakhaError(
            code="type_mismatch",
            technical="Could not infer expression type.",
            line=getattr(expr, "line", 1),
            column=getattr(expr, "column", 1),
        )

    def _infer_call_type(self, expr: Call) -> str:
        if expr.callee == "max":
            if len(expr.args) != 2:
                raise PatakhaError(
                    code="arity_mismatch",
                    technical="`max` expects 2 arguments.",
                    line=expr.line,
                    column=expr.column,
                )
            a = self._infer_expr_type(expr.args[0])
            b = self._infer_expr_type(expr.args[1])
            if not _is_numeric(a) or not _is_numeric(b):
                raise PatakhaError(
                    code="type_mismatch",
                    technical="`max` expects numeric arguments.",
                    line=expr.line,
                    column=expr.column,
                )
            return _numeric_result(a, b)

        if expr.callee == "len":
            if len(expr.args) != 1:
                raise PatakhaError(
                    code="arity_mismatch",
                    technical="`len` expects 1 argument.",
                    line=expr.line,
                    column=expr.column,
                )
            t = self._infer_expr_type(expr.args[0])
            if t != "text" and not _is_array(t):
                raise PatakhaError(
                    code="type_mismatch",
                    technical="`len` supports text/array arguments.",
                    line=expr.line,
                    column=expr.column,
                )
            return "int"

        if expr.callee in {"input", "bata"}:
            if len(expr.args) != 0:
                raise PatakhaError(
                    code="arity_mismatch",
                    technical="`bata` expects no arguments.",
                    line=expr.line,
                    column=expr.column,
                )
            return "int"

        sig = self.function_sigs.get(expr.callee)
        if sig is None:
            suggestion = _did_you_mean(expr.callee, list(BUILTINS) + list(self.function_sigs.keys()))
            hint = f" Did you mean `{suggestion}`?" if suggestion else ""
            raise PatakhaError(
                code="undeclared_function",
                technical=f"Function `{expr.callee}` is not declared.{hint}",
                line=expr.line,
                column=expr.column,
            )
        if len(expr.args) != len(sig.params):
            raise PatakhaError(
                code="arity_mismatch",
                technical=(
                    f"Function `{expr.callee}` expects {len(sig.params)} argument(s), "
                    f"got {len(expr.args)}."
                ),
                line=expr.line,
                column=expr.column,
            )
        for arg, (_, ptype) in zip(expr.args, sig.params):
            at = self._infer_expr_type(arg)
            if not _is_assignable(ptype, at):
                raise PatakhaError(
                    code="type_mismatch",
                    technical=f"Argument type mismatch: expected {ptype}, got {at}.",
                    line=expr.line,
                    column=expr.column,
                )
        return sig.return_type

    def _eval_constant(self, expr: Expr) -> int | float | bool | None:
        if isinstance(expr, Literal):
            if isinstance(expr.value, (int, float, bool)):
                return expr.value
            return None
        if isinstance(expr, Unary):
            v = self._eval_constant(expr.operand)
            if v is None:
                return None
            if expr.op == "-":
                if isinstance(v, int):
                    return -int(v)
                return -float(v)
            if expr.op == "!":
                return not bool(v)
            return None
        if isinstance(expr, Cast):
            v = self._eval_constant(expr.expr)
            if v is None:
                return None
            if expr.type_name == "int":
                return int(v)
            if expr.type_name == "float":
                return float(v)
            if expr.type_name == "bool":
                return bool(v)
            return None
        if isinstance(expr, Binary):
            left = self._eval_constant(expr.left)
            right = self._eval_constant(expr.right)
            if left is None or right is None:
                return None
            try:
                if expr.op == "+":
                    if isinstance(left, int) and isinstance(right, int):
                        return int(left) + int(right)
                    return float(left) + float(right)
                if expr.op == "-":
                    if isinstance(left, int) and isinstance(right, int):
                        return int(left) - int(right)
                    return float(left) - float(right)
                if expr.op == "*":
                    if isinstance(left, int) and isinstance(right, int):
                        return int(left) * int(right)
                    return float(left) * float(right)
                if expr.op == "/":
                    if float(right) == 0:
                        return None
                    return float(left) / float(right)
                if expr.op == "%":
                    if float(right) == 0:
                        return None
                    return int(left) % int(right)
                if expr.op == "<":
                    return float(left) < float(right)
                if expr.op == "<=":
                    return float(left) <= float(right)
                if expr.op == ">":
                    return float(left) > float(right)
                if expr.op == ">=":
                    return float(left) >= float(right)
                if expr.op == "==":
                    return left == right
                if expr.op == "!=":
                    return left != right
                if expr.op == "&&":
                    return bool(left) and bool(right)
                if expr.op == "||":
                    return bool(left) or bool(right)
            except Exception:
                return None
        return None

    def _declare_var(self, name: str, type_name: str, line: int, column: int) -> None:
        current = self.scopes[-1]
        if name in current:
            raise PatakhaError(
                code="redeclared_variable",
                technical=f"Variable `{name}` is already declared in this scope.",
                line=line,
                column=column,
            )
        current[name] = VarSymbol(type_name=type_name, line=line, column=column)
        self.locals_by_function.setdefault(self.current_function, set()).add(name)

    def _lookup(self, name: str, line: int, column: int) -> VarSymbol:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        suggestion = _did_you_mean(
            name,
            [k for scope in self.scopes for k in scope.keys()] + list(KEYWORD_HINTS),
        )
        hint = f" Did you mean `{suggestion}`?" if suggestion else ""
        raise PatakhaError(
            code="undeclared_variable",
            technical=f"Variable `{name}` is not declared.{hint}",
            line=line,
            column=column,
        )

    def _resolve_type_name(self, type_name: str, allow_void: bool, line: int, column: int) -> str:
        t = type_name.strip()
        if t in PRIMITIVES:
            if t == "void" and not allow_void:
                raise PatakhaError(
                    code="type_mismatch",
                    technical="`khali` type not allowed here.",
                    line=line,
                    column=column,
                )
            return t
        if t in self.composite_types:
            c = self.composite_types[t]
            return f"{c.kind} {c.name}"
        suggestion = _did_you_mean(t, list(PRIMITIVES) + list(self.composite_types.keys()))
        hint = f" Did you mean `{suggestion}`?" if suggestion else ""
        raise PatakhaError(
            code="unknown_type",
            technical=f"Unknown type `{t}`.{hint}",
            line=line,
            column=column,
        )

    def _push_scope(self, scope_tag: str) -> None:
        self.scopes.append({})
        label = f"{self.current_function}:{scope_tag}:{self.scope_counter}"
        self.scope_counter += 1
        self.scope_names.append(label)

    def _pop_scope(self) -> None:
        symbols = self.scopes.pop()
        name = self.scope_names.pop()
        for var_name, sym in symbols.items():
            if not sym.used:
                self._warn(
                    code="unused_variable",
                    message=f"Variable `{var_name}` declared but never used.",
                    line=sym.line,
                    column=sym.column,
                )
        self.scope_snapshots.append((name, {k: v.type_name for k, v in symbols.items()}))

    def _warn(self, code: str, message: str, line: int, column: int) -> None:
        self.warnings.append(PatakhaWarning(code=code, message=message, line=line, column=column))


def _array_of(base: str, size: int) -> str:
    return f"array<{base},{size}>"


def _is_array(type_name: str) -> bool:
    return type_name.startswith("array<") and type_name.endswith(">")


def _array_elem(type_name: str) -> str:
    inner = type_name[len("array<") : -1]
    cut = inner.rfind(",")
    if cut == -1:
        return "int"
    return inner[:cut]


def _is_assignable(dst: str, src: str) -> bool:
    if dst == src:
        return True
    if dst in {"int", "bool"} and src in {"int", "bool"}:
        return True
    if dst == "float" and src in {"int", "float", "bool"}:
        return True
    return False


def _is_castable(src: str, dst: str) -> bool:
    if src == dst:
        return True
    if _is_numeric(src) and dst in {"int", "float", "bool"}:
        return True
    if src == "bool" and dst in {"int", "float", "bool"}:
        return True
    if src == "text" and dst == "text":
        return True
    return False


def _is_numeric(type_name: str) -> bool:
    return type_name in {"int", "float", "bool"}


def _numeric_result(left: str, right: str) -> str:
    if left == "float" or right == "float":
        return "float"
    return "int"


def _did_you_mean(name: str, candidates: list[str]) -> str | None:
    if not name or not candidates:
        return None
    matches = difflib.get_close_matches(name, sorted(set(candidates)), n=1, cutoff=0.72)
    return matches[0] if matches else None


def _composite_name(type_name: str) -> str | None:
    if type_name.startswith("struct "):
        return type_name.split(" ", 1)[1]
    if type_name.startswith("class "):
        return type_name.split(" ", 1)[1]
    return None
