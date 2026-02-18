from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass
class FieldDecl:
    type_name: str
    name: str
    array_size: int | None
    line: int
    column: int


@dataclass
class TypeDecl:
    kind: str  # "struct" | "class"
    name: str
    fields: list[FieldDecl]
    line: int
    column: int


@dataclass
class Param:
    type_name: str
    name: str
    line: int
    column: int


@dataclass
class Program:
    type_decls: list[TypeDecl]
    functions: list["FunctionDecl"]
    statements: list["Stmt"]
    imports: list[str] = field(default_factory=list)


@dataclass
class Block:
    statements: list["Stmt"]
    line: int
    column: int


@dataclass
class VarDecl:
    name: str
    init: "Expr | None"
    line: int
    column: int
    type_name: str = "int"
    array_size: int | None = None


@dataclass
class Assign:
    name: str
    value: "Expr"
    line: int
    column: int
    target: "Expr | None" = None


@dataclass
class IfStmt:
    condition: "Expr"
    then_block: Block
    else_block: Block | None
    line: int
    column: int


@dataclass
class WhileStmt:
    condition: "Expr"
    body: Block
    line: int
    column: int


@dataclass
class ForStmt:
    init: "Stmt | None"
    condition: "Expr | None"
    post: "Stmt | None"
    body: Block
    line: int
    column: int


@dataclass
class DoWhileStmt:
    body: Block
    condition: "Expr"
    line: int
    column: int


@dataclass
class CaseClause:
    value: "Expr"
    block: Block
    line: int
    column: int


@dataclass
class SwitchStmt:
    condition: "Expr"
    cases: list[CaseClause]
    default_block: Block | None
    line: int
    column: int


@dataclass
class BreakStmt:
    line: int
    column: int


@dataclass
class ContinueStmt:
    line: int
    column: int


@dataclass
class PrintStmt:
    value: "Expr"
    line: int
    column: int


@dataclass
class ReturnStmt:
    value: "Expr | None"
    line: int
    column: int


@dataclass
class ExprStmt:
    expr: "Expr"
    line: int
    column: int


@dataclass
class FunctionDecl:
    name: str
    params: list[str]
    body: Block
    line: int
    column: int
    return_type: str = "int"
    typed_params: list[Param] | None = None


@dataclass
class Identifier:
    name: str
    line: int
    column: int


@dataclass
class Literal:
    value: int | float | bool | str
    line: int
    column: int


@dataclass
class Unary:
    op: str
    operand: "Expr"
    line: int
    column: int


@dataclass
class Binary:
    op: str
    left: "Expr"
    right: "Expr"
    line: int
    column: int


@dataclass
class Call:
    callee: str
    args: list["Expr"]
    line: int
    column: int


@dataclass
class IndexAccess:
    base: "Expr"
    index: "Expr"
    line: int
    column: int


@dataclass
class MemberAccess:
    base: "Expr"
    member: str
    line: int
    column: int


@dataclass
class Cast:
    type_name: str
    expr: "Expr"
    line: int
    column: int


Stmt = Union[
    VarDecl,
    Assign,
    IfStmt,
    WhileStmt,
    ForStmt,
    DoWhileStmt,
    SwitchStmt,
    BreakStmt,
    ContinueStmt,
    PrintStmt,
    ReturnStmt,
    ExprStmt,
    Block,
]
Expr = Union[Identifier, Literal, Unary, Binary, Call, IndexAccess, MemberAccess, Cast]
