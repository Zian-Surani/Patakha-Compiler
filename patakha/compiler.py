from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from patakha.ast_nodes import (
    Assign,
    Binary,
    Block,
    BreakStmt,
    Cast,
    Call,
    ContinueStmt,
    DoWhileStmt,
    ExprStmt,
    ForStmt,
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
from patakha.codegen_c import generate_c_code
from patakha.codegen_stack import generate_stack_code
from patakha.diagnostics import PatakhaAggregateError, PatakhaError
from patakha.ir import IRFunction, IRGenerator, IRResult, Instruction
from patakha.lexer import Lexer
from patakha.optimizer import CFG, optimize_function
from patakha.parser import Parser
from patakha.semantic import SemanticAnalyzer, SemanticResult
from patakha.token import Token


@dataclass
class CompilationResult:
    tokens: list[Token]
    ast: Program
    semantic: SemanticResult
    ir_raw: IRResult
    ir_optimized: IRResult
    cfg_by_function: dict[str, CFG]
    c_code: str
    stack_code: str


@dataclass
class _ParsedUnit:
    path: Path
    tokens: list[Token]
    ast: Program
    deps: list[Path]


def compile_source(
    source: str,
    optimize: bool = True,
    source_name: str | Path | None = None,
) -> CompilationResult:
    source_path: Path | None = None
    if source_name is not None:
        source_path = Path(source_name).resolve()

    if source_path is not None:
        tokens, ast = _parse_with_imports(source, source_path)
    else:
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        ast = parser.parse()
        if ast.imports:
            raise PatakhaError(
                code="missing_import",
                technical="Import resolution needs a source file path context.",
                line=1,
                column=1,
            )

    semantic = SemanticAnalyzer().analyze(ast)

    ir_raw: IRResult = IRResult(functions=[])
    ir_optimized: IRResult = IRResult(functions=[])
    cfg_by_function: dict[str, CFG] = {}
    try:
        ir_raw = IRGenerator().generate(ast)
        ir_optimized = copy.deepcopy(ir_raw)
        if optimize:
            optimized_functions: list[IRFunction] = []
            for fn in ir_optimized.functions:
                optimized_fn, cfg = optimize_function(fn)
                optimized_functions.append(optimized_fn)
                cfg_by_function[fn.name] = cfg
            ir_optimized = IRResult(functions=optimized_functions)
        else:
            for fn in ir_optimized.functions:
                cfg_by_function[fn.name] = CFG(function_name=fn.name, blocks=[])
    except Exception:
        ir_raw = IRResult(functions=[])
        ir_optimized = IRResult(functions=[])
        cfg_by_function = {}

    c_code = generate_c_code(program=ast, semantic=semantic)
    stack_code = generate_stack_code(program=ast)

    return CompilationResult(
        tokens=tokens,
        ast=ast,
        semantic=semantic,
        ir_raw=ir_raw,
        ir_optimized=ir_optimized,
        cfg_by_function=cfg_by_function,
        c_code=c_code,
        stack_code=stack_code,
    )


def compile_file(path: str | Path, optimize: bool = True) -> CompilationResult:
    source_path = Path(path).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    return compile_source(source_text, optimize=optimize, source_name=source_path)


def _parse_with_imports(source_text: str, source_path: Path) -> tuple[list[Token], Program]:
    units: dict[Path, _ParsedUnit] = {}
    visiting: list[Path] = []
    entry = _collect_unit(
        source_path,
        units=units,
        visiting=visiting,
        source_override=source_text,
    )
    order = _dependency_order(entry.path, units)

    merged_types = []
    merged_functions = []
    for mod_path in order:
        if mod_path == entry.path:
            continue
        mod = units[mod_path]
        if mod.ast.statements:
            raise PatakhaError(
                code="module_has_main",
                technical=f"Imported module `{mod_path}` cannot contain main statements.",
                line=1,
                column=1,
            )
        merged_types.extend(mod.ast.type_decls)
        merged_functions.extend(mod.ast.functions)

    merged_types.extend(entry.ast.type_decls)
    merged_functions.extend(entry.ast.functions)

    merged_program = Program(
        type_decls=merged_types,
        functions=merged_functions,
        statements=entry.ast.statements,
        imports=list(entry.ast.imports),
    )
    return entry.tokens, merged_program


def _collect_unit(
    path: Path,
    units: dict[Path, _ParsedUnit],
    visiting: list[Path],
    source_override: str | None = None,
) -> _ParsedUnit:
    if path in units:
        return units[path]
    if path in visiting:
        cycle = " -> ".join(str(p) for p in [*visiting, path])
        raise PatakhaError(
            code="circular_import",
            technical=f"Circular import detected: {cycle}",
            line=1,
            column=1,
        )

    if source_override is None:
        if not path.exists():
            raise PatakhaError(
                code="missing_import",
                technical=f"Imported module not found: `{path}`.",
                line=1,
                column=1,
            )
        source_text = path.read_text(encoding="utf-8")
    else:
        source_text = source_override

    visiting.append(path)
    try:
        try:
            tokens = Lexer(source_text).tokenize()
            ast = Parser(tokens).parse()
        except PatakhaAggregateError as agg:
            wrapped = [
                PatakhaError(
                    code=e.code,
                    technical=f"{e.technical} (in `{path}`)",
                    line=e.line,
                    column=e.column,
                )
                for e in agg.errors
            ]
            raise PatakhaAggregateError(wrapped) from agg
        except PatakhaError as err:
            raise PatakhaError(
                code=err.code,
                technical=f"{err.technical} (in `{path}`)",
                line=err.line,
                column=err.column,
            ) from err
        deps = [_resolve_import_path(path.parent, imp) for imp in ast.imports]
        unit = _ParsedUnit(path=path, tokens=tokens, ast=ast, deps=deps)
        units[path] = unit
        for dep in deps:
            _collect_unit(dep, units=units, visiting=visiting)
        return unit
    finally:
        visiting.pop()


def _resolve_import_path(base_dir: Path, import_path: str) -> Path:
    raw = Path(import_path)
    candidate = raw if raw.is_absolute() else (base_dir / raw)
    if candidate.suffix == "":
        candidate = candidate.with_suffix(".bhai")
    candidate = candidate.resolve()
    if not candidate.exists():
        raise PatakhaError(
            code="missing_import",
            technical=f"Imported module not found: `{candidate}`.",
            line=1,
            column=1,
        )
    return candidate


def _dependency_order(entry: Path, units: dict[Path, _ParsedUnit]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []

    def walk(path: Path) -> None:
        if path in seen:
            return
        seen.add(path)
        for dep in units[path].deps:
            walk(dep)
        out.append(path)

    walk(entry)
    return out


def format_tokens(tokens: list[Token]) -> str:
    rows: list[str] = []
    for tok in tokens:
        rows.append(f"{tok.line}:{tok.column}  {tok.kind:<12} {tok.value!r}")
    return "\n".join(rows) + "\n"


def format_ir(ir_result: IRResult) -> str:
    rows: list[str] = []
    for fn in ir_result.functions:
        rows.append(f"func {fn.name}({', '.join(fn.params)}):")
        for ins in fn.instructions:
            rows.append(f"  {ins}")
        if not fn.instructions:
            rows.append("  <empty>")
        rows.append("")
    return "\n".join(rows).rstrip() + "\n"


def format_ast(program: Program) -> str:
    lines: list[str] = []
    lines.append("Program")
    if program.imports:
        lines.append("  Imports")
        for imp in program.imports:
            lines.append(f"    {imp}")
    for td in program.type_decls:
        lines.append(f"  {td.kind.title()} {td.name}")
        for f in td.fields:
            suffix = f"[{f.array_size}]" if f.array_size is not None else ""
            lines.append(f"    Field {f.type_name} {f.name}{suffix}")
    for fn in program.functions:
        r = fn.return_type
        params = ", ".join(
            f"{p.type_name} {p.name}" for p in (fn.typed_params or [])
        ) or ", ".join(fn.params)
        lines.append(f"  Function {r} {fn.name}({params})")
        _fmt_block(fn.body, lines, indent="    ")
    lines.append("  Main")
    for stmt in program.statements:
        _fmt_stmt(stmt, lines, indent="    ")
    return "\n".join(lines) + "\n"


def format_symbols(result: SemanticResult) -> str:
    lines: list[str] = []
    lines.append("Types")
    for name, kind in sorted(result.composite_kinds.items()):
        lines.append(f"  {kind} {name}")
        for fname, ftype in sorted(result.composite_fields.get(name, {}).items()):
            lines.append(f"    {fname}: {ftype}")
    if not result.composite_kinds:
        lines.append("  <none>")
    lines.append("")

    lines.append("Functions")
    for name, arity in sorted(result.function_signatures.items()):
        rt = result.function_return_types.get(name, "int")
        pt = ", ".join(result.function_param_types.get(name, []))
        lines.append(f"  {name}/{arity} -> {rt} ({pt})")
    if not result.function_signatures:
        lines.append("  <none>")
    lines.append("")

    lines.append("Locals by function")
    for name, symbols in sorted(result.locals_by_function.items()):
        joined = ", ".join(sorted(symbols)) if symbols else "<none>"
        lines.append(f"  {name}: {joined}")
    lines.append("")

    lines.append("Scope snapshots")
    for scope_name, symbols in result.scope_snapshots:
        if symbols:
            joined = ", ".join(f"{k}:{v}" for k, v in sorted(symbols.items()))
        else:
            joined = "<empty>"
        lines.append(f"  {scope_name} => {joined}")
    lines.append("")

    lines.append("Warnings")
    if result.warnings:
        for w in result.warnings:
            lines.append(f"  {w.line}:{w.column} [{w.code}] {w.message}")
    else:
        lines.append("  <none>")
    return "\n".join(lines) + "\n"


def format_cfg(cfg_by_function: dict[str, CFG]) -> str:
    lines: list[str] = []
    for name, cfg in sorted(cfg_by_function.items()):
        lines.append(f"CFG {name}")
        if not cfg.blocks:
            lines.append("  <no-blocks>")
            lines.append("")
            continue
        for block in cfg.blocks:
            succ = ",".join(str(x) for x in sorted(block.successors)) or "-"
            pred = ",".join(str(x) for x in sorted(block.predecessors)) or "-"
            lines.append(f"  B{block.block_id} pred[{pred}] succ[{succ}]")
            for ins in block.instructions:
                lines.append(f"    {ins}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_ast_dot(program: Program) -> str:
    lines: list[str] = ["digraph AST {", "  node [shape=box];"]
    counter = {"n": 0}

    def new_id() -> str:
        nid = f"n{counter['n']}"
        counter["n"] += 1
        return nid

    def emit_node(label: str) -> str:
        nid = new_id()
        safe = label.replace('"', '\\"')
        lines.append(f'  {nid} [label="{safe}"];')
        return nid

    def emit_edge(a: str, b: str) -> None:
        lines.append(f"  {a} -> {b};")

    root = emit_node("Program")
    imports_id = emit_node("Imports")
    emit_edge(root, imports_id)
    for imp in program.imports:
        emit_edge(imports_id, emit_node(imp))

    types_id = emit_node("Types")
    emit_edge(root, types_id)
    for td in program.type_decls:
        t = emit_node(f"{td.kind} {td.name}")
        emit_edge(types_id, t)
        for f in td.fields:
            suffix = f"[{f.array_size}]" if f.array_size is not None else ""
            emit_edge(t, emit_node(f"{f.type_name} {f.name}{suffix}"))

    funcs_id = emit_node("Functions")
    emit_edge(root, funcs_id)
    for fn in program.functions:
        ptxt = ", ".join(fn.params)
        f = emit_node(f"{fn.return_type} {fn.name}({ptxt})")
        emit_edge(funcs_id, f)
        _ast_dot_block(fn.body, f, emit_node, emit_edge)

    main_id = emit_node("Main")
    emit_edge(root, main_id)
    for stmt in program.statements:
        sid = _ast_dot_stmt(stmt, emit_node, emit_edge)
        emit_edge(main_id, sid)

    lines.append("}")
    return "\n".join(lines) + "\n"


def format_cfg_dot(cfg_by_function: dict[str, CFG]) -> str:
    lines: list[str] = ["digraph CFG {", "  node [shape=rectangle];"]
    for fn_name, cfg in sorted(cfg_by_function.items()):
        lines.append(f"  subgraph cluster_{fn_name} {{")
        lines.append(f'    label="{fn_name}";')
        for b in cfg.blocks:
            label_lines = [f"B{b.block_id}"] + [str(ins) for ins in b.instructions]
            safe = "\\l".join(x.replace('"', '\\"') for x in label_lines) + "\\l"
            lines.append(f'    {fn_name}_B{b.block_id} [label="{safe}"];')
        for b in cfg.blocks:
            for s in sorted(b.successors):
                lines.append(f"    {fn_name}_B{b.block_id} -> {fn_name}_B{s};")
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _fmt_block(block: Block, lines: list[str], indent: str) -> None:
    lines.append(f"{indent}Block")
    for stmt in block.statements:
        _fmt_stmt(stmt, lines, indent + "  ")


def _fmt_stmt(stmt: object, lines: list[str], indent: str) -> None:
    if isinstance(stmt, VarDecl):
        suffix = f"[{stmt.array_size}]" if stmt.array_size is not None else ""
        lines.append(f"{indent}VarDecl {stmt.type_name} {stmt.name}{suffix}")
        if stmt.init is not None:
            _fmt_expr(stmt.init, lines, indent + "  ")
        return
    if isinstance(stmt, Assign):
        lines.append(f"{indent}Assign")
        _fmt_expr(stmt.target or Identifier(stmt.name, stmt.line, stmt.column), lines, indent + "  ")
        _fmt_expr(stmt.value, lines, indent + "  ")
        return
    if isinstance(stmt, IfStmt):
        lines.append(f"{indent}If")
        _fmt_expr(stmt.condition, lines, indent + "  ")
        _fmt_block(stmt.then_block, lines, indent + "  ")
        if stmt.else_block:
            lines.append(f"{indent}Else")
            _fmt_block(stmt.else_block, lines, indent + "  ")
        return
    if isinstance(stmt, WhileStmt):
        lines.append(f"{indent}While")
        _fmt_expr(stmt.condition, lines, indent + "  ")
        _fmt_block(stmt.body, lines, indent + "  ")
        return
    if isinstance(stmt, ForStmt):
        lines.append(f"{indent}For")
        if stmt.init:
            _fmt_stmt(stmt.init, lines, indent + "  ")
        if stmt.condition:
            _fmt_expr(stmt.condition, lines, indent + "  ")
        if stmt.post:
            _fmt_stmt(stmt.post, lines, indent + "  ")
        _fmt_block(stmt.body, lines, indent + "  ")
        return
    if isinstance(stmt, DoWhileStmt):
        lines.append(f"{indent}DoWhile")
        _fmt_block(stmt.body, lines, indent + "  ")
        _fmt_expr(stmt.condition, lines, indent + "  ")
        return
    if isinstance(stmt, SwitchStmt):
        lines.append(f"{indent}Switch")
        _fmt_expr(stmt.condition, lines, indent + "  ")
        for case in stmt.cases:
            lines.append(f"{indent}  Case")
            _fmt_expr(case.value, lines, indent + "    ")
            _fmt_block(case.block, lines, indent + "    ")
        if stmt.default_block is not None:
            lines.append(f"{indent}  Default")
            _fmt_block(stmt.default_block, lines, indent + "    ")
        return
    if isinstance(stmt, BreakStmt):
        lines.append(f"{indent}Break")
        return
    if isinstance(stmt, ContinueStmt):
        lines.append(f"{indent}Continue")
        return
    if isinstance(stmt, PrintStmt):
        lines.append(f"{indent}Print")
        _fmt_expr(stmt.value, lines, indent + "  ")
        return
    if isinstance(stmt, ReturnStmt):
        lines.append(f"{indent}Return")
        if stmt.value is not None:
            _fmt_expr(stmt.value, lines, indent + "  ")
        return
    if isinstance(stmt, ExprStmt):
        lines.append(f"{indent}ExprStmt")
        _fmt_expr(stmt.expr, lines, indent + "  ")
        return
    if isinstance(stmt, Block):
        _fmt_block(stmt, lines, indent)


def _fmt_expr(expr: object, lines: list[str], indent: str) -> None:
    if isinstance(expr, Identifier):
        lines.append(f"{indent}Identifier {expr.name}")
        return
    if isinstance(expr, Literal):
        lines.append(f"{indent}Literal {expr.value!r}")
        return
    if isinstance(expr, Unary):
        lines.append(f"{indent}Unary {expr.op}")
        _fmt_expr(expr.operand, lines, indent + "  ")
        return
    if isinstance(expr, Binary):
        lines.append(f"{indent}Binary {expr.op}")
        _fmt_expr(expr.left, lines, indent + "  ")
        _fmt_expr(expr.right, lines, indent + "  ")
        return
    if isinstance(expr, Call):
        lines.append(f"{indent}Call {expr.callee}")
        for arg in expr.args:
            _fmt_expr(arg, lines, indent + "  ")
        return
    if isinstance(expr, IndexAccess):
        lines.append(f"{indent}Index")
        _fmt_expr(expr.base, lines, indent + "  ")
        _fmt_expr(expr.index, lines, indent + "  ")
        return
    if isinstance(expr, MemberAccess):
        lines.append(f"{indent}Member .{expr.member}")
        _fmt_expr(expr.base, lines, indent + "  ")
        return
    if isinstance(expr, Cast):
        lines.append(f"{indent}Cast {expr.type_name}")
        _fmt_expr(expr.expr, lines, indent + "  ")


def _ast_dot_block(
    block: Block,
    parent: str,
    emit_node: callable,
    emit_edge: callable,
) -> None:
    b = emit_node("Block")
    emit_edge(parent, b)
    for stmt in block.statements:
        s = _ast_dot_stmt(stmt, emit_node, emit_edge)
        emit_edge(b, s)


def _ast_dot_stmt(stmt: object, emit_node: callable, emit_edge: callable) -> str:
    if isinstance(stmt, VarDecl):
        suffix = f"[{stmt.array_size}]" if stmt.array_size is not None else ""
        n = emit_node(f"VarDecl {stmt.type_name} {stmt.name}{suffix}")
        if stmt.init is not None:
            e = _ast_dot_expr(stmt.init, emit_node, emit_edge)
            emit_edge(n, e)
        return n
    if isinstance(stmt, Assign):
        n = emit_node("Assign")
        t = _ast_dot_expr(stmt.target or Identifier(stmt.name, stmt.line, stmt.column), emit_node, emit_edge)
        v = _ast_dot_expr(stmt.value, emit_node, emit_edge)
        emit_edge(n, t)
        emit_edge(n, v)
        return n
    if isinstance(stmt, IfStmt):
        n = emit_node("If")
        c = _ast_dot_expr(stmt.condition, emit_node, emit_edge)
        emit_edge(n, c)
        _ast_dot_block(stmt.then_block, n, emit_node, emit_edge)
        if stmt.else_block:
            _ast_dot_block(stmt.else_block, n, emit_node, emit_edge)
        return n
    if isinstance(stmt, WhileStmt):
        n = emit_node("While")
        emit_edge(n, _ast_dot_expr(stmt.condition, emit_node, emit_edge))
        _ast_dot_block(stmt.body, n, emit_node, emit_edge)
        return n
    if isinstance(stmt, ForStmt):
        n = emit_node("For")
        if stmt.init:
            emit_edge(n, _ast_dot_stmt(stmt.init, emit_node, emit_edge))
        if stmt.condition:
            emit_edge(n, _ast_dot_expr(stmt.condition, emit_node, emit_edge))
        if stmt.post:
            emit_edge(n, _ast_dot_stmt(stmt.post, emit_node, emit_edge))
        _ast_dot_block(stmt.body, n, emit_node, emit_edge)
        return n
    if isinstance(stmt, DoWhileStmt):
        n = emit_node("DoWhile")
        _ast_dot_block(stmt.body, n, emit_node, emit_edge)
        emit_edge(n, _ast_dot_expr(stmt.condition, emit_node, emit_edge))
        return n
    if isinstance(stmt, SwitchStmt):
        n = emit_node("Switch")
        emit_edge(n, _ast_dot_expr(stmt.condition, emit_node, emit_edge))
        for case in stmt.cases:
            c = emit_node("Case")
            emit_edge(c, _ast_dot_expr(case.value, emit_node, emit_edge))
            _ast_dot_block(case.block, c, emit_node, emit_edge)
            emit_edge(n, c)
        if stmt.default_block is not None:
            d = emit_node("Default")
            _ast_dot_block(stmt.default_block, d, emit_node, emit_edge)
            emit_edge(n, d)
        return n
    if isinstance(stmt, BreakStmt):
        return emit_node("Break")
    if isinstance(stmt, ContinueStmt):
        return emit_node("Continue")
    if isinstance(stmt, PrintStmt):
        n = emit_node("Print")
        emit_edge(n, _ast_dot_expr(stmt.value, emit_node, emit_edge))
        return n
    if isinstance(stmt, ReturnStmt):
        n = emit_node("Return")
        if stmt.value is not None:
            emit_edge(n, _ast_dot_expr(stmt.value, emit_node, emit_edge))
        return n
    if isinstance(stmt, ExprStmt):
        n = emit_node("ExprStmt")
        emit_edge(n, _ast_dot_expr(stmt.expr, emit_node, emit_edge))
        return n
    if isinstance(stmt, Block):
        n = emit_node("Block")
        for s in stmt.statements:
            emit_edge(n, _ast_dot_stmt(s, emit_node, emit_edge))
        return n
    return emit_node("UnknownStmt")


def _ast_dot_expr(expr: object, emit_node: callable, emit_edge: callable) -> str:
    if isinstance(expr, Identifier):
        return emit_node(f"Id {expr.name}")
    if isinstance(expr, Literal):
        return emit_node(f"Lit {expr.value!r}")
    if isinstance(expr, Unary):
        n = emit_node(f"Unary {expr.op}")
        emit_edge(n, _ast_dot_expr(expr.operand, emit_node, emit_edge))
        return n
    if isinstance(expr, Binary):
        n = emit_node(f"Binary {expr.op}")
        emit_edge(n, _ast_dot_expr(expr.left, emit_node, emit_edge))
        emit_edge(n, _ast_dot_expr(expr.right, emit_node, emit_edge))
        return n
    if isinstance(expr, Call):
        n = emit_node(f"Call {expr.callee}")
        for a in expr.args:
            emit_edge(n, _ast_dot_expr(a, emit_node, emit_edge))
        return n
    if isinstance(expr, IndexAccess):
        n = emit_node("Index")
        emit_edge(n, _ast_dot_expr(expr.base, emit_node, emit_edge))
        emit_edge(n, _ast_dot_expr(expr.index, emit_node, emit_edge))
        return n
    if isinstance(expr, MemberAccess):
        n = emit_node(f"Member .{expr.member}")
        emit_edge(n, _ast_dot_expr(expr.base, emit_node, emit_edge))
        return n
    if isinstance(expr, Cast):
        n = emit_node(f"Cast {expr.type_name}")
        emit_edge(n, _ast_dot_expr(expr.expr, emit_node, emit_edge))
        return n
    return emit_node("UnknownExpr")
