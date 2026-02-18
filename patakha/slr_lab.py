from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Production:
    lhs: str
    rhs: tuple[str, ...]


@dataclass(frozen=True)
class Item:
    prod_idx: int
    dot: int


@dataclass
class SLRArtifacts:
    productions: list[Production]
    states: list[set[Item]]
    action: dict[tuple[int, str], str]
    goto: dict[tuple[int, str], int]
    follow: dict[str, set[str]]
    conflicts: list[tuple[int, str, str, str]]


def build_demo_slr() -> SLRArtifacts:
    productions = [
        Production("S'", ("E",)),
        Production("E", ("E", "+", "T")),
        Production("E", ("T",)),
        Production("T", ("T", "*", "F")),
        Production("T", ("F",)),
        Production("F", ("(", "E", ")")),
        Production("F", ("id",)),
    ]
    nonterminals = {"S'", "E", "T", "F"}
    terminals = {"+", "*", "(", ")", "id", "$"}

    def closure(items: set[Item]) -> set[Item]:
        out = set(items)
        changed = True
        while changed:
            changed = False
            for item in list(out):
                prod = productions[item.prod_idx]
                if item.dot >= len(prod.rhs):
                    continue
                symbol = prod.rhs[item.dot]
                if symbol in nonterminals:
                    for idx, p in enumerate(productions):
                        if p.lhs == symbol:
                            new_item = Item(idx, 0)
                            if new_item not in out:
                                out.add(new_item)
                                changed = True
        return out

    def goto(items: set[Item], symbol: str) -> set[Item]:
        moved = set()
        for item in items:
            prod = productions[item.prod_idx]
            if item.dot < len(prod.rhs) and prod.rhs[item.dot] == symbol:
                moved.add(Item(item.prod_idx, item.dot + 1))
        return closure(moved)

    states: list[set[Item]] = []
    transitions: dict[tuple[int, str], int] = {}

    start = closure({Item(0, 0)})
    states.append(start)
    queue = [0]

    symbols = (terminals - {"$"}) | nonterminals
    while queue:
        idx = queue.pop(0)
        for symbol in symbols:
            target = goto(states[idx], symbol)
            if not target:
                continue
            try:
                target_idx = next(i for i, s in enumerate(states) if s == target)
            except StopIteration:
                target_idx = len(states)
                states.append(target)
                queue.append(target_idx)
            transitions[(idx, symbol)] = target_idx

    follow = _follow_sets(productions, "S'")
    action: dict[tuple[int, str], str] = {}
    goto_table: dict[tuple[int, str], int] = {}
    conflicts: list[tuple[int, str, str, str]] = []

    for state_idx, state in enumerate(states):
        for item in state:
            prod = productions[item.prod_idx]
            if item.dot < len(prod.rhs):
                symbol = prod.rhs[item.dot]
                target = transitions.get((state_idx, symbol))
                if target is None:
                    continue
                if symbol in terminals:
                    _set_action(action, conflicts, state_idx, symbol, f"s{target}")
                else:
                    goto_table[(state_idx, symbol)] = target
                continue

            if prod.lhs == "S'":
                _set_action(action, conflicts, state_idx, "$", "acc")
                continue

            prod_id = item.prod_idx
            for term in follow[prod.lhs]:
                _set_action(action, conflicts, state_idx, term, f"r{prod_id}")

    return SLRArtifacts(
        productions=productions,
        states=states,
        action=action,
        goto=goto_table,
        follow=follow,
        conflicts=conflicts,
    )


def slr_parse_trace(tokens: list[str], artifacts: SLRArtifacts) -> list[str]:
    stream = list(tokens)
    if not stream or stream[-1] != "$":
        stream.append("$")

    stack: list[int] = [0]
    index = 0
    trace: list[str] = []

    while True:
        state = stack[-1]
        lookahead = stream[index]
        action = artifacts.action.get((state, lookahead))
        trace.append(f"state={state} lookahead={lookahead} action={action}")

        if action is None:
            trace.append("error")
            break
        if action == "acc":
            trace.append("accept")
            break
        if action.startswith("s"):
            stack.append(int(action[1:]))
            index += 1
            continue
        if action.startswith("r"):
            prod = artifacts.productions[int(action[1:])]
            for _ in prod.rhs:
                stack.pop()
            top = stack[-1]
            next_state = artifacts.goto.get((top, prod.lhs))
            if next_state is None:
                trace.append("error goto-missing")
                break
            stack.append(next_state)
            trace.append(f"reduce {prod.lhs} -> {' '.join(prod.rhs)}")
            continue
    return trace


def format_slr_artifacts(artifacts: SLRArtifacts, parse_trace: list[str] | None = None) -> str:
    lines: list[str] = []
    lines.append("SLR Demo Grammar Productions")
    for idx, prod in enumerate(artifacts.productions):
        lines.append(f"  ({idx}) {prod.lhs} -> {' '.join(prod.rhs)}")
    lines.append("")
    lines.append("FOLLOW sets")
    for nt in sorted(artifacts.follow):
        vals = ", ".join(sorted(artifacts.follow[nt]))
        lines.append(f"  FOLLOW({nt}) = {{ {vals} }}")
    lines.append("")
    lines.append("LR(0) States")
    for i, state in enumerate(artifacts.states):
        lines.append(f"  I{i}")
        for item in sorted(state, key=lambda it: (it.prod_idx, it.dot)):
            prod = artifacts.productions[item.prod_idx]
            rhs = list(prod.rhs)
            rhs.insert(item.dot, "•")
            lines.append(f"    {prod.lhs} -> {' '.join(rhs)}")
    lines.append("")
    lines.append("ACTION table")
    for key in sorted(artifacts.action):
        state, term = key
        lines.append(f"  ACTION[{state}, {term}] = {artifacts.action[key]}")
    lines.append("")
    lines.append("GOTO table")
    for key in sorted(artifacts.goto):
        state, nt = key
        lines.append(f"  GOTO[{state}, {nt}] = {artifacts.goto[key]}")
    lines.append("")
    lines.append("Conflicts")
    if artifacts.conflicts:
        for st, sym, old, new in artifacts.conflicts:
            lines.append(f"  ({st}, {sym}) {old} <-> {new}")
    else:
        lines.append("  <none>")
    if parse_trace is not None:
        lines.append("")
        lines.append("Parse trace")
        for row in parse_trace:
            lines.append(f"  {row}")
    return "\n".join(lines) + "\n"


def _set_action(
    table: dict[tuple[int, str], str],
    conflicts: list[tuple[int, str, str, str]],
    state: int,
    symbol: str,
    value: str,
) -> None:
    key = (state, symbol)
    if key in table and table[key] != value:
        conflicts.append((state, symbol, table[key], value))
    else:
        table[key] = value


def _follow_sets(productions: list[Production], start: str) -> dict[str, set[str]]:
    nonterminals = {prod.lhs for prod in productions}
    first: dict[str, set[str]] = {nt: set() for nt in nonterminals}

    changed = True
    while changed:
        changed = False
        for prod in productions:
            if not prod.rhs:
                continue
            head = prod.rhs[0]
            if head in nonterminals:
                before = set(first[prod.lhs])
                first[prod.lhs] |= first[head]
                if first[prod.lhs] != before:
                    changed = True
            else:
                before = set(first[prod.lhs])
                first[prod.lhs].add(head)
                if first[prod.lhs] != before:
                    changed = True

    follow = {nt: set() for nt in nonterminals}
    follow[start].add("$")

    changed = True
    while changed:
        changed = False
        for prod in productions:
            rhs = list(prod.rhs)
            for i, symbol in enumerate(rhs):
                if symbol not in nonterminals:
                    continue
                trailer = rhs[i + 1 :]
                before = set(follow[symbol])
                if not trailer:
                    follow[symbol] |= follow[prod.lhs]
                else:
                    next_sym = trailer[0]
                    if next_sym in nonterminals:
                        follow[symbol] |= first[next_sym]
                    else:
                        follow[symbol].add(next_sym)
                if follow[symbol] != before:
                    changed = True
    return follow

