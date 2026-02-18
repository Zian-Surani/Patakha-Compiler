from __future__ import annotations

from patakha.ast_nodes import (
    Assign,
    Binary,
    Block,
    BreakStmt,
    CaseClause,
    Call,
    ContinueStmt,
    DoWhileStmt,
    Expr,
    ExprStmt,
    FieldDecl,
    ForStmt,
    FunctionDecl,
    Identifier,
    IfStmt,
    IndexAccess,
    Literal,
    MemberAccess,
    Cast,
    Param,
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
from patakha.diagnostics import PatakhaAggregateError, PatakhaError
from patakha.token import Token


BIN_OPS = {
    "OR": "||",
    "AND": "&&",
    "EQ": "==",
    "NEQ": "!=",
    "LT": "<",
    "LTE": "<=",
    "GT": ">",
    "GTE": ">=",
    "PLUS": "+",
    "MINUS": "-",
    "STAR": "*",
    "SLASH": "/",
    "MOD": "%",
}


SYNC_TOKENS = {
    "IMPORT",
    "BHAI",
    "DECIMAL",
    "BOOL",
    "TEXT",
    "STRUCT",
    "CLASS",
    "AGAR",
    "WARNA",
    "JABTAK",
    "FOR",
    "DO",
    "SWITCH",
    "CASE",
    "DEFAULT",
    "BREAK",
    "CONTINUE",
    "BOL",
    "NIKAL",
    "LBRACE",
    "RBRACE",
    "BAS_KAR",
    "KAAM",
    "START_BHAI",
}


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.index = 0
        self.errors: list[PatakhaError] = []
        self.known_types: set[str] = set()

    def parse(self) -> Program:
        imports: list[str] = []
        type_decls: list[TypeDecl] = []
        functions: list[FunctionDecl] = []

        while not self._check("START_BHAI") and not self._check("EOF"):
            checkpoint = self.index
            try:
                if self._match("IMPORT"):
                    imports.append(self._parse_import_decl())
                elif self._check("STRUCT") or self._check("CLASS"):
                    type_decls.append(self._parse_type_decl())
                elif self._check("KAAM"):
                    functions.append(self._parse_function())
                else:
                    tok = self._current()
                    raise PatakhaError(
                        code="unexpected_token",
                        technical=(
                            "Only `import`, `struct`, `kaksha`, or `kaam` declarations allowed "
                            "before `shuru`."
                        ),
                        line=tok.line,
                        column=tok.column,
                    )
            except PatakhaError as err:
                self.errors.append(err)
                self._synchronize_top_level()
            if self.index == checkpoint and not self._is_at_end():
                self._advance()

        if not self._match("START_BHAI"):
            tok = self._current()
            self.errors.append(
                PatakhaError(
                    code="expected_start",
                    technical="Program should start with `shuru`.",
                    line=tok.line,
                    column=tok.column,
                )
            )
            self._seek_to("START_BHAI")
            self._match("START_BHAI")

        statements: list[Stmt] = []
        while not self._check("BAS_KAR") and not self._check("EOF"):
            checkpoint = self.index
            try:
                statements.append(self._parse_statement())
            except PatakhaError as err:
                self.errors.append(err)
                self._synchronize()
            if self.index == checkpoint and not self._is_at_end():
                self._advance()

        if not self._match("BAS_KAR"):
            tok = self._current()
            self.errors.append(
                PatakhaError(
                    code="expected_end",
                    technical="Program should end with `bass`.",
                    line=tok.line,
                    column=tok.column,
                )
            )

        if not self._check("EOF"):
            tok = self._current()
            self.errors.append(
                PatakhaError(
                    code="unexpected_token",
                    technical="Unexpected tokens found after `bass`.",
                    line=tok.line,
                    column=tok.column,
                )
            )

        program = Program(type_decls=type_decls, functions=functions, statements=statements, imports=imports)
        if self.errors:
            raise PatakhaAggregateError(self.errors)
        return program

    def _parse_import_decl(self) -> str:
        path_tok = self._expect(
            "STRING",
            code="invalid_statement",
            technical="Expected import path string after `import`.",
        )
        self._consume_optional_semicolon()
        return str(path_tok.value)

    def _parse_type_decl(self) -> TypeDecl:
        kind_tok = self._advance()
        if kind_tok.kind not in {"STRUCT", "CLASS"}:
            raise PatakhaError(
                code="unexpected_token",
                technical="Expected `struct` or `kaksha`.",
                line=kind_tok.line,
                column=kind_tok.column,
            )
        name_tok = self._expect(
            "IDENT",
            code="invalid_statement",
            technical=f"Expected name after `{kind_tok.value}`.",
        )
        self._expect(
            "LBRACE",
            code="missing_lbrace",
            technical=f"Expected `{{` in {kind_tok.value} declaration.",
        )
        fields: list[FieldDecl] = []
        while not self._check("RBRACE"):
            if self._check("EOF"):
                eof = self._current()
                raise PatakhaError(
                    code="missing_rbrace",
                    technical="Expected `}` to close type declaration.",
                    line=eof.line,
                    column=eof.column,
                )
            type_name, _, _ = self._parse_type_spec(allow_void=False)
            field_name_tok = self._expect(
                "IDENT",
                code="invalid_statement",
                technical="Expected field name in type declaration.",
            )
            array_size = None
            if self._match("LBRACKET"):
                sz = self._expect(
                    "NUMBER",
                    code="invalid_statement",
                    technical="Expected numeric array size.",
                )
                array_size = int(sz.value)
                self._expect(
                    "RBRACKET",
                    code="unexpected_token",
                    technical="Expected `]` after array size.",
                )
            self._consume_optional_semicolon()
            fields.append(
                FieldDecl(
                    type_name=type_name,
                    name=str(field_name_tok.value),
                    array_size=array_size,
                    line=field_name_tok.line,
                    column=field_name_tok.column,
                )
            )
        self._expect(
            "RBRACE",
            code="missing_rbrace",
            technical="Expected `}` to close type declaration.",
        )
        self._match("SEMICOLON")
        type_name = str(name_tok.value)
        self.known_types.add(type_name)
        return TypeDecl(
            kind="struct" if kind_tok.kind == "STRUCT" else "class",
            name=type_name,
            fields=fields,
            line=kind_tok.line,
            column=kind_tok.column,
        )

    def _parse_function(self) -> FunctionDecl:
        fn_tok = self._expect(
            "KAAM",
            code="invalid_function",
            technical="Expected `kaam` at function declaration.",
        )

        if self._check("IDENT") and self._peek_kind(1) == "LPAREN":
            return_type = "int"
            name_tok = self._advance()
            self._expect(
                "LPAREN",
                code="missing_lparen",
                technical="Expected `(` after function name.",
            )
            typed_params: list[Param] = []
            if not self._check("RPAREN"):
                p = self._expect(
                    "IDENT",
                    code="invalid_params",
                    technical="Expected parameter name.",
                )
                typed_params.append(Param(type_name="int", name=str(p.value), line=p.line, column=p.column))
                while self._match("COMMA"):
                    p = self._expect(
                        "IDENT",
                        code="invalid_params",
                        technical="Expected parameter name after comma.",
                    )
                    typed_params.append(
                        Param(type_name="int", name=str(p.value), line=p.line, column=p.column)
                    )
            self._expect(
                "RPAREN",
                code="missing_rparen",
                technical="Expected `)` after parameters.",
            )
            body = self._parse_block()
            return FunctionDecl(
                name=str(name_tok.value),
                params=[p.name for p in typed_params],
                body=body,
                line=fn_tok.line,
                column=fn_tok.column,
                return_type=return_type,
                typed_params=typed_params,
            )

        return_type, _, _ = self._parse_type_spec(allow_void=True)
        name_tok = self._expect(
            "IDENT",
            code="invalid_function",
            technical="Expected function name.",
        )
        self._expect(
            "LPAREN",
            code="missing_lparen",
            technical="Expected `(` after function name.",
        )
        typed_params: list[Param] = []
        if not self._check("RPAREN"):
            typed_params.append(self._parse_param())
            while self._match("COMMA"):
                typed_params.append(self._parse_param())
        self._expect(
            "RPAREN",
            code="missing_rparen",
            technical="Expected `)` after parameters.",
        )
        body = self._parse_block()
        return FunctionDecl(
            name=str(name_tok.value),
            params=[p.name for p in typed_params],
            body=body,
            line=fn_tok.line,
            column=fn_tok.column,
            return_type=return_type,
            typed_params=typed_params,
        )

    def _parse_param(self) -> Param:
        if self._check("IDENT") and self._peek_kind(1) in {"COMMA", "RPAREN"}:
            name_tok = self._advance()
            return Param(type_name="int", name=str(name_tok.value), line=name_tok.line, column=name_tok.column)
        type_name, _, _ = self._parse_type_spec(allow_void=False)
        name_tok = self._expect(
            "IDENT",
            code="invalid_params",
            technical="Expected parameter name.",
        )
        return Param(type_name=type_name, name=str(name_tok.value), line=name_tok.line, column=name_tok.column)

    def _parse_statement(self) -> Stmt:
        if self._check("LBRACE"):
            return self._parse_block()
        if self._is_var_decl_start():
            return self._parse_var_decl_statement()
        if self._match("AGAR"):
            return self._parse_if(self._previous())
        if self._match("JABTAK"):
            return self._parse_while(self._previous())
        if self._match("FOR"):
            return self._parse_for(self._previous())
        if self._match("DO"):
            return self._parse_do_while(self._previous())
        if self._match("SWITCH"):
            return self._parse_switch(self._previous())
        if self._match("BREAK"):
            tok = self._previous()
            self._consume_optional_semicolon()
            return BreakStmt(line=tok.line, column=tok.column)
        if self._match("CONTINUE"):
            tok = self._previous()
            self._consume_optional_semicolon()
            return ContinueStmt(line=tok.line, column=tok.column)
        if self._match("BOL"):
            return self._parse_print(self._previous())
        if self._match("NIKAL"):
            return self._parse_return(self._previous())
        return self._parse_assignment_or_expr_statement(expect_semicolon=True)

    def _parse_var_decl_statement(self) -> VarDecl:
        type_name, _, type_tok = self._parse_type_spec(allow_void=False)
        name_token = self._expect(
            "IDENT",
            code="invalid_statement",
            technical="Expected variable name in declaration.",
        )
        array_size = None
        if self._match("LBRACKET"):
            size_tok = self._expect(
                "NUMBER",
                code="invalid_statement",
                technical="Expected numeric array size.",
            )
            array_size = int(size_tok.value)
            self._expect(
                "RBRACKET",
                code="unexpected_token",
                technical="Expected `]` after array size.",
            )
        init: Expr | None = None
        if self._match("ASSIGN"):
            init = self._parse_expression()
        self._consume_optional_semicolon()
        return VarDecl(
            name=str(name_token.value),
            init=init,
            line=type_tok.line,
            column=type_tok.column,
            type_name=type_name,
            array_size=array_size,
        )

    def _parse_if(self, if_token: Token) -> IfStmt:
        self._expect(
            "LPAREN",
            code="missing_lparen",
            technical="Expected `(` after `agar`.",
        )
        condition = self._parse_expression()
        self._expect(
            "RPAREN",
            code="missing_rparen",
            technical="Expected `)` after if condition.",
        )
        then_block = self._parse_block()
        else_block: Block | None = None
        if self._match("WARNA"):
            else_block = self._parse_block()
        return IfStmt(
            condition=condition,
            then_block=then_block,
            else_block=else_block,
            line=if_token.line,
            column=if_token.column,
        )

    def _parse_while(self, while_token: Token) -> WhileStmt:
        self._expect(
            "LPAREN",
            code="missing_lparen",
            technical="Expected `(` after `tabtak`.",
        )
        condition = self._parse_expression()
        self._expect(
            "RPAREN",
            code="missing_rparen",
            technical="Expected `)` after while condition.",
        )
        body = self._parse_block()
        return WhileStmt(
            condition=condition,
            body=body,
            line=while_token.line,
            column=while_token.column,
        )

    def _parse_for(self, for_token: Token) -> ForStmt:
        self._expect(
            "LPAREN",
            code="missing_lparen",
            technical="Expected `(` after `jabtak`.",
        )
        init: Stmt | None = None
        if not self._check("SEMICOLON"):
            if self._is_var_decl_start():
                init = self._parse_for_var_decl()
            else:
                init = self._parse_assignment_or_expr_statement(expect_semicolon=False)
        self._expect(
            "SEMICOLON",
            code="missing_semicolon",
            technical="Expected `;` after jabtak-init.",
        )
        condition: Expr | None = None
        if not self._check("SEMICOLON"):
            condition = self._parse_expression()
        self._expect(
            "SEMICOLON",
            code="missing_semicolon",
            technical="Expected `;` after jabtak-condition.",
        )
        post: Stmt | None = None
        if not self._check("RPAREN"):
            post = self._parse_assignment_or_expr_statement(expect_semicolon=False)
        self._expect(
            "RPAREN",
            code="missing_rparen",
            technical="Expected `)` after jabtak-clause.",
        )
        body = self._parse_block()
        return ForStmt(
            init=init,
            condition=condition,
            post=post,
            body=body,
            line=for_token.line,
            column=for_token.column,
        )

    def _parse_do_while(self, do_token: Token) -> DoWhileStmt:
        body = self._parse_block()
        self._expect(
            "JABTAK",
            code="invalid_statement",
            technical="Expected `tabtak` after `kar` block.",
        )
        self._expect(
            "LPAREN",
            code="missing_lparen",
            technical="Expected `(` after `tabtak`.",
        )
        condition = self._parse_expression()
        self._expect(
            "RPAREN",
            code="missing_rparen",
            technical="Expected `)` after do-while condition.",
        )
        self._consume_optional_semicolon()
        return DoWhileStmt(body=body, condition=condition, line=do_token.line, column=do_token.column)

    def _parse_switch(self, switch_token: Token) -> SwitchStmt:
        self._expect(
            "LPAREN",
            code="missing_lparen",
            technical="Expected `(` after `switch`.",
        )
        condition = self._parse_expression()
        self._expect(
            "RPAREN",
            code="missing_rparen",
            technical="Expected `)` after switch condition.",
        )
        self._expect(
            "LBRACE",
            code="missing_lbrace",
            technical="Expected `{` after switch condition.",
        )

        cases: list[CaseClause] = []
        default_block: Block | None = None
        while not self._check("RBRACE"):
            if self._check("EOF"):
                eof = self._current()
                raise PatakhaError(
                    code="missing_rbrace",
                    technical="Expected `}` to close switch block.",
                    line=eof.line,
                    column=eof.column,
                )

            if self._match("CASE"):
                case_tok = self._previous()
                case_value = self._parse_expression()
                self._expect(
                    "COLON",
                    code="unexpected_token",
                    technical="Expected `:` after case label.",
                )
                case_statements: list[Stmt] = []
                while (
                    not self._check("CASE")
                    and not self._check("DEFAULT")
                    and not self._check("RBRACE")
                    and not self._check("EOF")
                ):
                    case_statements.append(self._parse_statement())
                cases.append(
                    CaseClause(
                        value=case_value,
                        block=Block(
                            statements=case_statements,
                            line=case_tok.line,
                            column=case_tok.column,
                        ),
                        line=case_tok.line,
                        column=case_tok.column,
                    )
                )
                continue

            if self._match("DEFAULT"):
                default_tok = self._previous()
                if default_block is not None:
                    raise PatakhaError(
                        code="duplicate_default",
                        technical="Only one `default` block is allowed in switch.",
                        line=default_tok.line,
                        column=default_tok.column,
                    )
                self._expect(
                    "COLON",
                    code="unexpected_token",
                    technical="Expected `:` after `default`.",
                )
                default_statements: list[Stmt] = []
                while (
                    not self._check("CASE")
                    and not self._check("DEFAULT")
                    and not self._check("RBRACE")
                    and not self._check("EOF")
                ):
                    default_statements.append(self._parse_statement())
                default_block = Block(
                    statements=default_statements,
                    line=default_tok.line,
                    column=default_tok.column,
                )
                continue

            tok = self._current()
            raise PatakhaError(
                code="unexpected_token",
                technical="Expected `case` or `default` inside switch block.",
                line=tok.line,
                column=tok.column,
            )

        self._expect(
            "RBRACE",
            code="missing_rbrace",
            technical="Expected `}` to close switch block.",
        )
        return SwitchStmt(
            condition=condition,
            cases=cases,
            default_block=default_block,
            line=switch_token.line,
            column=switch_token.column,
        )

    def _parse_print(self, print_token: Token) -> PrintStmt:
        self._expect(
            "LPAREN",
            code="missing_lparen",
            technical="Expected `(` after `bol`.",
        )
        value = self._parse_expression()
        self._expect(
            "RPAREN",
            code="missing_rparen",
            technical="Expected `)` after print expression.",
        )
        self._consume_optional_semicolon()
        return PrintStmt(value=value, line=print_token.line, column=print_token.column)

    def _parse_return(self, return_token: Token) -> ReturnStmt:
        value: Expr | None = None
        if not self._is_return_boundary_at_current():
            value = self._parse_expression()
        self._consume_optional_semicolon()
        return ReturnStmt(value=value, line=return_token.line, column=return_token.column)

    def _parse_block(self) -> Block:
        lbrace = self._expect(
            "LBRACE",
            code="missing_lbrace",
            technical="Expected `{` to start block.",
        )
        statements: list[Stmt] = []
        while not self._check("RBRACE"):
            if self._check("EOF"):
                eof = self._current()
                raise PatakhaError(
                    code="missing_rbrace",
                    technical="Expected `}` before end of file.",
                    line=eof.line,
                    column=eof.column,
                )
            checkpoint = self.index
            try:
                statements.append(self._parse_statement())
            except PatakhaError as err:
                self.errors.append(err)
                self._synchronize(in_block=True)
            if self.index == checkpoint and not self._is_at_end():
                self._advance()
        self._expect(
            "RBRACE",
            code="missing_rbrace",
            technical="Expected `}` to close block.",
        )
        return Block(statements=statements, line=lbrace.line, column=lbrace.column)

    def _parse_assignment_or_expr_statement(self, expect_semicolon: bool) -> Stmt:
        if self._match("INCR", "DECR"):
            op_token = self._previous()
            target = self._parse_postfix()
            if not isinstance(target, (Identifier, IndexAccess, MemberAccess)):
                raise PatakhaError(
                    code="invalid_statement",
                    technical="Increment/decrement target must be variable/field/index.",
                    line=op_token.line,
                    column=op_token.column,
                )
            value = Binary(
                op="+" if op_token.kind == "INCR" else "-",
                left=target,
                right=Literal(value=1, line=op_token.line, column=op_token.column),
                line=op_token.line,
                column=op_token.column,
            )
            if expect_semicolon:
                self._consume_optional_semicolon()
            return Assign(
                name=target.name if isinstance(target, Identifier) else "",
                value=value,
                line=target.line,
                column=target.column,
                target=target,
            )

        expr = self._parse_expression()
        if self._match(
            "ASSIGN",
            "PLUS_ASSIGN",
            "MINUS_ASSIGN",
            "STAR_ASSIGN",
            "SLASH_ASSIGN",
            "MOD_ASSIGN",
            "INCR",
            "DECR",
        ):
            op_token = self._previous()
            if not isinstance(expr, (Identifier, IndexAccess, MemberAccess)):
                raise PatakhaError(
                    code="invalid_statement",
                    technical="Left side of assignment must be variable/field/index.",
                    line=op_token.line,
                    column=op_token.column,
                )
            if op_token.kind == "ASSIGN":
                value = self._parse_expression()
            elif op_token.kind in {"PLUS_ASSIGN", "MINUS_ASSIGN", "STAR_ASSIGN", "SLASH_ASSIGN", "MOD_ASSIGN"}:
                rhs = self._parse_expression()
                op_map = {
                    "PLUS_ASSIGN": "+",
                    "MINUS_ASSIGN": "-",
                    "STAR_ASSIGN": "*",
                    "SLASH_ASSIGN": "/",
                    "MOD_ASSIGN": "%",
                }
                value = Binary(
                    op=op_map[op_token.kind],
                    left=expr,
                    right=rhs,
                    line=op_token.line,
                    column=op_token.column,
                )
            else:
                value = Binary(
                    op="+" if op_token.kind == "INCR" else "-",
                    left=expr,
                    right=Literal(value=1, line=op_token.line, column=op_token.column),
                    line=op_token.line,
                    column=op_token.column,
                )
            if expect_semicolon:
                self._consume_optional_semicolon()
            return Assign(
                name=expr.name if isinstance(expr, Identifier) else "",
                value=value,
                line=getattr(expr, "line", self._current().line),
                column=getattr(expr, "column", self._current().column),
                target=expr,
            )
        if expect_semicolon:
            self._consume_optional_semicolon()
        return ExprStmt(
            expr=expr,
            line=getattr(expr, "line", self._current().line),
            column=getattr(expr, "column", self._current().column),
        )

    def _parse_for_var_decl(self) -> VarDecl:
        type_name, _, type_tok = self._parse_type_spec(allow_void=False)
        name_token = self._expect(
            "IDENT",
            code="invalid_statement",
            technical="Expected variable name in declaration.",
        )
        array_size = None
        if self._match("LBRACKET"):
            size_tok = self._expect(
                "NUMBER",
                code="invalid_statement",
                technical="Expected numeric array size.",
            )
            array_size = int(size_tok.value)
            self._expect(
                "RBRACKET",
                code="unexpected_token",
                technical="Expected `]` after array size.",
            )
        init: Expr | None = None
        if self._match("ASSIGN"):
            init = self._parse_expression()
        return VarDecl(
            name=str(name_token.value),
            init=init,
            line=type_tok.line,
            column=type_tok.column,
            type_name=type_name,
            array_size=array_size,
        )

    def _parse_expression(self) -> Expr:
        return self._parse_or()

    def _parse_or(self) -> Expr:
        expr = self._parse_and()
        while self._match("OR"):
            op_token = self._previous()
            op = BIN_OPS[op_token.kind]
            right = self._parse_and()
            expr = Binary(op=op, left=expr, right=right, line=op_token.line, column=op_token.column)
        return expr

    def _parse_and(self) -> Expr:
        expr = self._parse_equality()
        while self._match("AND"):
            op_token = self._previous()
            op = BIN_OPS[op_token.kind]
            right = self._parse_equality()
            expr = Binary(op=op, left=expr, right=right, line=op_token.line, column=op_token.column)
        return expr

    def _parse_equality(self) -> Expr:
        expr = self._parse_relational()
        while self._match("EQ", "NEQ"):
            op_token = self._previous()
            op = BIN_OPS[op_token.kind]
            right = self._parse_relational()
            expr = Binary(op=op, left=expr, right=right, line=op_token.line, column=op_token.column)
        return expr

    def _parse_relational(self) -> Expr:
        expr = self._parse_term()
        while self._match("LT", "LTE", "GT", "GTE"):
            op_token = self._previous()
            op = BIN_OPS[op_token.kind]
            right = self._parse_term()
            expr = Binary(op=op, left=expr, right=right, line=op_token.line, column=op_token.column)
        return expr

    def _parse_term(self) -> Expr:
        expr = self._parse_factor()
        while self._match("PLUS", "MINUS"):
            op_token = self._previous()
            op = BIN_OPS[op_token.kind]
            right = self._parse_factor()
            expr = Binary(op=op, left=expr, right=right, line=op_token.line, column=op_token.column)
        return expr

    def _parse_factor(self) -> Expr:
        expr = self._parse_unary()
        while self._match("STAR", "SLASH", "MOD"):
            op_token = self._previous()
            op = BIN_OPS[op_token.kind]
            right = self._parse_unary()
            expr = Binary(op=op, left=expr, right=right, line=op_token.line, column=op_token.column)
        return expr

    def _parse_unary(self) -> Expr:
        if self._match("NOT"):
            op_token = self._previous()
            return Unary(op="!", operand=self._parse_unary(), line=op_token.line, column=op_token.column)
        if self._match("MINUS"):
            op_token = self._previous()
            return Unary(op="-", operand=self._parse_unary(), line=op_token.line, column=op_token.column)
        if self._is_cast_start():
            type_name, _, type_tok = self._parse_type_spec(allow_void=False)
            self._expect(
                "LPAREN",
                code="missing_lparen",
                technical="Expected `(` after cast type.",
            )
            operand = self._parse_expression()
            self._expect(
                "RPAREN",
                code="missing_rparen",
                technical="Expected `)` after cast expression.",
            )
            return Cast(type_name=type_name, expr=operand, line=type_tok.line, column=type_tok.column)
        return self._parse_postfix()

    def _is_cast_start(self) -> bool:
        return self._current().kind in {"BHAI", "DECIMAL", "BOOL", "TEXT"} and self._peek_kind(1) == "LPAREN"

    def _parse_postfix(self) -> Expr:
        expr = self._parse_primary()
        while True:
            if self._match("LPAREN"):
                args: list[Expr] = []
                if not self._check("RPAREN"):
                    args.append(self._parse_expression())
                    while self._match("COMMA"):
                        args.append(self._parse_expression())
                self._expect(
                    "RPAREN",
                    code="missing_rparen",
                    technical="Expected `)` after call arguments.",
                )
                if not isinstance(expr, Identifier):
                    raise PatakhaError(
                        code="invalid_expression",
                        technical="Only function identifiers can be called.",
                        line=getattr(expr, "line", self._current().line),
                        column=getattr(expr, "column", self._current().column),
                    )
                expr = Call(callee=expr.name, args=args, line=expr.line, column=expr.column)
                continue
            if self._match("LBRACKET"):
                idx = self._parse_expression()
                rb = self._expect(
                    "RBRACKET",
                    code="unexpected_token",
                    technical="Expected `]` after index.",
                )
                expr = IndexAccess(base=expr, index=idx, line=rb.line, column=rb.column)
                continue
            if self._match("DOT"):
                member_tok = self._expect(
                    "IDENT",
                    code="invalid_expression",
                    technical="Expected member name after `.`.",
                )
                expr = MemberAccess(
                    base=expr,
                    member=str(member_tok.value),
                    line=member_tok.line,
                    column=member_tok.column,
                )
                continue
            return expr

    def _parse_primary(self) -> Expr:
        if self._match("NUMBER"):
            tok = self._previous()
            return Literal(value=int(tok.value), line=tok.line, column=tok.column)
        if self._match("FLOAT"):
            tok = self._previous()
            return Literal(value=float(tok.value), line=tok.line, column=tok.column)
        if self._match("STRING"):
            tok = self._previous()
            return Literal(value=str(tok.value), line=tok.line, column=tok.column)
        if self._match("SACH"):
            tok = self._previous()
            return Literal(value=True, line=tok.line, column=tok.column)
        if self._match("JHOOTH"):
            tok = self._previous()
            return Literal(value=False, line=tok.line, column=tok.column)
        if self._match("IDENT"):
            tok = self._previous()
            return Identifier(name=str(tok.value), line=tok.line, column=tok.column)
        if self._match("LPAREN"):
            expr = self._parse_expression()
            self._expect(
                "RPAREN",
                code="missing_rparen",
                technical="Expected `)` after expression.",
            )
            return expr

        tok = self._current()
        raise PatakhaError(
            code="invalid_expression",
            technical=f"Unexpected token `{tok.value}` in expression.",
            line=tok.line,
            column=tok.column,
        )

    def _parse_type_spec(self, allow_void: bool) -> tuple[str, str | None, Token]:
        if self._match("BHAI"):
            tok = self._previous()
            return "int", None, tok
        if self._match("DECIMAL"):
            tok = self._previous()
            return "float", None, tok
        if self._match("BOOL"):
            tok = self._previous()
            return "bool", None, tok
        if self._match("TEXT"):
            tok = self._previous()
            return "text", None, tok
        if self._match("VOID"):
            tok = self._previous()
            if not allow_void:
                raise PatakhaError(
                    code="type_mismatch",
                    technical="`khali` type not allowed here.",
                    line=tok.line,
                    column=tok.column,
                )
            return "void", None, tok
        if self._match("STRUCT"):
            tok = self._previous()
            name = self._expect(
                "IDENT",
                code="invalid_statement",
                technical="Expected struct type name.",
            )
            return str(name.value), "struct", tok
        if self._match("CLASS"):
            tok = self._previous()
            name = self._expect(
                "IDENT",
                code="invalid_statement",
                technical="Expected kaksha type name.",
            )
            return str(name.value), "class", tok
        if self._check("IDENT") and str(self._current().value) in self.known_types:
            tok = self._advance()
            return str(tok.value), None, tok

        tok = self._current()
        raise PatakhaError(
            code="invalid_statement",
            technical="Expected a type name.",
            line=tok.line,
            column=tok.column,
        )

    def _is_var_decl_start(self) -> bool:
        cur = self._current()
        if cur.kind in {"BHAI", "DECIMAL", "BOOL", "TEXT"}:
            return self._peek_kind(1) == "IDENT"
        if cur.kind in {"STRUCT", "CLASS"}:
            return self._peek_kind(1) == "IDENT" and self._peek_kind(2) == "IDENT"
        if cur.kind == "IDENT" and str(cur.value) in self.known_types and self._peek_kind(1) == "IDENT":
            return True
        return False

    def _match(self, *kinds: str) -> bool:
        for kind in kinds:
            if self._check(kind):
                self._advance()
                return True
        return False

    def _expect(self, kind: str, code: str, technical: str) -> Token:
        if self._check(kind):
            return self._advance()
        tok = self._current()
        raise PatakhaError(code=code, technical=technical, line=tok.line, column=tok.column)

    def _check(self, kind: str) -> bool:
        return self._current().kind == kind

    def _consume_optional_semicolon(self) -> None:
        self._match("SEMICOLON")

    def _is_return_boundary(self, kind: str) -> bool:
        return kind in {
            "SEMICOLON",
            "RBRACE",
            "BAS_KAR",
            "EOF",
            "AGAR",
            "WARNA",
            "JABTAK",
            "FOR",
            "DO",
            "SWITCH",
            "CASE",
            "DEFAULT",
            "BREAK",
            "CONTINUE",
            "BOL",
            "NIKAL",
        }

    def _is_return_boundary_at_current(self) -> bool:
        kind = self._current().kind
        if self._is_return_boundary(kind):
            return True
        if kind in {"BHAI", "DECIMAL", "BOOL", "TEXT"}:
            return self._peek_kind(1) == "IDENT"
        if kind in {"STRUCT", "CLASS"}:
            return self._peek_kind(1) == "IDENT" and self._peek_kind(2) == "IDENT"
        return False

    def _peek_kind(self, distance: int) -> str:
        idx = self.index + distance
        if idx >= len(self.tokens):
            return "EOF"
        return self.tokens[idx].kind

    def _advance(self) -> Token:
        if not self._is_at_end():
            self.index += 1
        return self._previous()

    def _is_at_end(self) -> bool:
        return self._current().kind == "EOF"

    def _current(self) -> Token:
        return self.tokens[self.index]

    def _previous(self) -> Token:
        if self.index == 0:
            return self.tokens[0]
        return self.tokens[self.index - 1]

    def _seek_to(self, kind: str) -> None:
        while not self._check("EOF") and not self._check(kind):
            self._advance()

    def _synchronize(self, in_block: bool = False) -> None:
        while not self._is_at_end():
            if self._previous().kind == "SEMICOLON":
                return
            current = self._current().kind
            if current in SYNC_TOKENS:
                if in_block and current == "RBRACE":
                    return
                if current != "RBRACE":
                    return
            self._advance()

    def _synchronize_top_level(self) -> None:
        while not self._is_at_end():
            if self._current().kind in {"IMPORT", "STRUCT", "CLASS", "KAAM", "START_BHAI"}:
                return
            self._advance()
