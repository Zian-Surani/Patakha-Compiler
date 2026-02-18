from __future__ import annotations

from dataclasses import dataclass


EPS = "EPS"


Grammar = dict[str, list[list[str]]]


@dataclass
class LL1Artifacts:
    grammar: Grammar
    start_symbol: str
    terminals: set[str]
    nonterminals: set[str]
    first: dict[str, set[str]]
    follow: dict[str, set[str]]
    table: dict[tuple[str, str], list[str]]
    conflicts: list[tuple[str, str, list[str], list[str]]]


def patakha_ll1_grammar() -> tuple[Grammar, str]:
    grammar: Grammar = {
        "Program": [["FuncDecls", "START_BHAI", "StmtList", "BAS_KAR", "EOF"]],
        "FuncDecls": [["KAAM", "IDENT", "LPAREN", "ParamsOpt", "RPAREN", "Block", "FuncDecls"], [EPS]],
        "ParamsOpt": [["IDENT", "ParamTail"], [EPS]],
        "ParamTail": [["COMMA", "IDENT", "ParamTail"], [EPS]],
        "Block": [["LBRACE", "StmtList", "RBRACE"]],
        "StmtList": [["Stmt", "StmtList"], [EPS]],
        "Stmt": [
            ["BHAI", "IDENT", "DeclTail", "SEMICOLON"],
            ["IDENT", "IdentStmtTail"],
            ["AGAR", "LPAREN", "Expr", "RPAREN", "Block", "ElsePart"],
            ["JABTAK", "LPAREN", "Expr", "RPAREN", "Block"],
            ["BOL", "LPAREN", "Expr", "RPAREN", "SEMICOLON"],
            ["NIKAL", "Expr", "SEMICOLON"],
            ["Block"],
        ],
        "DeclTail": [["ASSIGN", "Expr"], [EPS]],
        "IdentStmtTail": [
            ["ASSIGN", "Expr", "SEMICOLON"],
            ["LPAREN", "ArgListOpt", "RPAREN", "SEMICOLON"],
        ],
        "ElsePart": [["WARNA", "Block"], [EPS]],
        "ArgListOpt": [["Expr", "ArgTail"], [EPS]],
        "ArgTail": [["COMMA", "Expr", "ArgTail"], [EPS]],
        "Expr": [["OrExpr"]],
        "OrExpr": [["AndExpr", "OrTail"]],
        "OrTail": [["OR", "AndExpr", "OrTail"], [EPS]],
        "AndExpr": [["EqExpr", "AndTail"]],
        "AndTail": [["AND", "EqExpr", "AndTail"], [EPS]],
        "EqExpr": [["RelExpr", "EqTail"]],
        "EqTail": [["EQ", "RelExpr", "EqTail"], ["NEQ", "RelExpr", "EqTail"], [EPS]],
        "RelExpr": [["AddExpr", "RelTail"]],
        "RelTail": [
            ["LT", "AddExpr", "RelTail"],
            ["LTE", "AddExpr", "RelTail"],
            ["GT", "AddExpr", "RelTail"],
            ["GTE", "AddExpr", "RelTail"],
            [EPS],
        ],
        "AddExpr": [["MulExpr", "AddTail"]],
        "AddTail": [["PLUS", "MulExpr", "AddTail"], ["MINUS", "MulExpr", "AddTail"], [EPS]],
        "MulExpr": [["UnaryExpr", "MulTail"]],
        "MulTail": [["STAR", "UnaryExpr", "MulTail"], ["SLASH", "UnaryExpr", "MulTail"], [EPS]],
        "UnaryExpr": [["NOT", "UnaryExpr"], ["MINUS", "UnaryExpr"], ["Primary"]],
        "Primary": [
            ["NUMBER"],
            ["STRING"],
            ["SACH"],
            ["JHOOTH"],
            ["IDENT", "PrimaryTail"],
            ["LPAREN", "Expr", "RPAREN"],
        ],
        "PrimaryTail": [["LPAREN", "ArgListOpt", "RPAREN"], [EPS]],
    }
    return grammar, "Program"


def build_ll1_artifacts() -> LL1Artifacts:
    grammar, start = patakha_ll1_grammar()
    nonterminals = set(grammar.keys())
    terminals = _collect_terminals(grammar)
    first = compute_first_sets(grammar)
    follow = compute_follow_sets(grammar, start, first)
    table, conflicts = build_parse_table(grammar, first, follow)
    return LL1Artifacts(
        grammar=grammar,
        start_symbol=start,
        terminals=terminals,
        nonterminals=nonterminals,
        first=first,
        follow=follow,
        table=table,
        conflicts=conflicts,
    )


def compute_first_sets(grammar: Grammar) -> dict[str, set[str]]:
    nonterminals = set(grammar.keys())
    first = {nt: set() for nt in nonterminals}
    changed = True
    while changed:
        changed = False
        for nt, productions in grammar.items():
            for prod in productions:
                prod_first = _first_of_sequence(prod, first, nonterminals)
                before = set(first[nt])
                first[nt] |= prod_first
                if first[nt] != before:
                    changed = True
    return first


def compute_follow_sets(
    grammar: Grammar, start_symbol: str, first: dict[str, set[str]]
) -> dict[str, set[str]]:
    nonterminals = set(grammar.keys())
    follow = {nt: set() for nt in nonterminals}
    follow[start_symbol].add("EOF")

    changed = True
    while changed:
        changed = False
        for lhs, productions in grammar.items():
            for prod in productions:
                for i, symbol in enumerate(prod):
                    if symbol not in nonterminals:
                        continue
                    suffix = prod[i + 1 :]
                    suffix_first = _first_of_sequence(suffix or [EPS], first, nonterminals)
                    before = set(follow[symbol])
                    follow[symbol] |= (suffix_first - {EPS})
                    if EPS in suffix_first or not suffix:
                        follow[symbol] |= follow[lhs]
                    if follow[symbol] != before:
                        changed = True
    return follow


def build_parse_table(
    grammar: Grammar, first: dict[str, set[str]], follow: dict[str, set[str]]
) -> tuple[dict[tuple[str, str], list[str]], list[tuple[str, str, list[str], list[str]]]]:
    table: dict[tuple[str, str], list[str]] = {}
    conflicts: list[tuple[str, str, list[str], list[str]]] = []
    nonterminals = set(grammar.keys())

    for lhs, productions in grammar.items():
        for prod in productions:
            first_set = _first_of_sequence(prod, first, nonterminals)
            targets = set(first_set - {EPS})
            if EPS in first_set:
                targets |= follow[lhs]
            for term in targets:
                key = (lhs, term)
                if key in table and table[key] != prod:
                    conflicts.append((lhs, term, table[key], prod))
                else:
                    table[key] = prod
    return table, conflicts


def predictive_parse_trace(
    token_kinds: list[str],
    artifacts: LL1Artifacts,
) -> list[str]:
    stack = ["EOF", artifacts.start_symbol]
    input_tokens = list(token_kinds)
    if not input_tokens or input_tokens[-1] != "EOF":
        input_tokens.append("EOF")
    index = 0
    trace: list[str] = []

    while stack:
        top = stack.pop()
        lookahead = input_tokens[index] if index < len(input_tokens) else "EOF"

        if top == EPS:
            trace.append(f"epsilon")
            continue
        if top not in artifacts.nonterminals:
            if top == lookahead:
                trace.append(f"match {lookahead}")
                index += 1
                if top == "EOF":
                    break
            else:
                trace.append(f"error terminal expected={top} got={lookahead}")
                break
            continue

        prod = artifacts.table.get((top, lookahead))
        if prod is None:
            trace.append(f"error no-rule ({top}, {lookahead})")
            break
        rhs = " ".join(prod)
        trace.append(f"{top} -> {rhs}")
        for symbol in reversed(prod):
            if symbol != EPS:
                stack.append(symbol)
    return trace


def format_ll1_artifacts(artifacts: LL1Artifacts, parse_trace: list[str] | None = None) -> str:
    lines: list[str] = []
    lines.append("FIRST sets")
    for nt in sorted(artifacts.nonterminals):
        vals = ", ".join(sorted(artifacts.first[nt]))
        lines.append(f"  FIRST({nt}) = {{ {vals} }}")
    lines.append("")
    lines.append("FOLLOW sets")
    for nt in sorted(artifacts.nonterminals):
        vals = ", ".join(sorted(artifacts.follow[nt]))
        lines.append(f"  FOLLOW({nt}) = {{ {vals} }}")
    lines.append("")
    lines.append("LL(1) table entries")
    for key in sorted(artifacts.table.keys()):
        lhs, term = key
        rhs = " ".join(artifacts.table[key])
        lines.append(f"  M[{lhs}, {term}] = {rhs}")
    lines.append("")
    lines.append("Conflicts")
    if artifacts.conflicts:
        for lhs, term, old, new in artifacts.conflicts:
            lines.append(
                f"  ({lhs}, {term}): {' '.join(old)}  <->  {' '.join(new)}"
            )
    else:
        lines.append("  <none>")
    if parse_trace is not None:
        lines.append("")
        lines.append("Predictive parse trace")
        for step in parse_trace:
            lines.append(f"  {step}")
    return "\n".join(lines) + "\n"


def _collect_terminals(grammar: Grammar) -> set[str]:
    nonterminals = set(grammar.keys())
    terminals: set[str] = set()
    for productions in grammar.values():
        for prod in productions:
            for symbol in prod:
                if symbol != EPS and symbol not in nonterminals:
                    terminals.add(symbol)
    return terminals


def _first_of_sequence(
    sequence: list[str],
    first_sets: dict[str, set[str]],
    nonterminals: set[str],
) -> set[str]:
    if not sequence:
        return {EPS}
    out: set[str] = set()
    all_nullable = True
    for symbol in sequence:
        if symbol == EPS:
            out.add(EPS)
            continue
        if symbol not in nonterminals:
            out.add(symbol)
            all_nullable = False
            break
        out |= (first_sets[symbol] - {EPS})
        if EPS not in first_sets[symbol]:
            all_nullable = False
            break
    if all_nullable:
        out.add(EPS)
    return out
