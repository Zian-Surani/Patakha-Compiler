from __future__ import annotations

from dataclasses import dataclass

from patakha.ir import IRFunction, Instruction


BIN_OPS = {"add", "sub", "mul", "div", "lt", "le", "gt", "ge", "eq", "ne"}
DEF_OPS = BIN_OPS | {"copy", "neg"}
JUMP_OPS = {"goto", "ifz", "ifnz"}


@dataclass
class BasicBlock:
    block_id: int
    start_index: int
    end_index: int
    instructions: list[Instruction]
    successors: set[int]
    predecessors: set[int]


@dataclass
class CFG:
    function_name: str
    blocks: list[BasicBlock]


def optimize_function(function: IRFunction) -> tuple[IRFunction, CFG]:
    cfg = _build_cfg(function.name, function.instructions)
    reachable = _reachable_blocks(cfg)
    cfg = _filter_reachable(cfg, reachable)

    propagated_blocks = _constant_propagation(cfg)
    cfg = CFG(function_name=cfg.function_name, blocks=propagated_blocks)

    cse_blocks = _local_cse(cfg)
    cfg = CFG(function_name=cfg.function_name, blocks=cse_blocks)

    licm_blocks = _loop_invariant_code_motion(cfg)
    cfg = CFG(function_name=cfg.function_name, blocks=licm_blocks)

    dse_blocks = _dead_store_elimination(cfg)
    cfg = CFG(function_name=cfg.function_name, blocks=dse_blocks)

    optimized_instructions = _flatten_cfg(cfg)
    optimized_function = IRFunction(
        name=function.name,
        params=list(function.params),
        instructions=optimized_instructions,
        temp_vars=set(function.temp_vars),
        local_vars=set(function.local_vars),
    )
    return optimized_function, cfg


def _build_cfg(function_name: str, instructions: list[Instruction]) -> CFG:
    if not instructions:
        return CFG(function_name=function_name, blocks=[])

    label_to_index: dict[str, int] = {}
    for idx, ins in enumerate(instructions):
        if ins.op == "label" and isinstance(ins.result, str):
            label_to_index[ins.result] = idx

    leaders = {0}
    for idx, ins in enumerate(instructions):
        if ins.op in JUMP_OPS and isinstance(ins.result, str) and ins.result in label_to_index:
            leaders.add(label_to_index[ins.result])
        if ins.op in JUMP_OPS | {"return"} and idx + 1 < len(instructions):
            leaders.add(idx + 1)

    sorted_leaders = sorted(leaders)
    blocks: list[BasicBlock] = []
    index_to_block: dict[int, int] = {}

    for block_id, start in enumerate(sorted_leaders):
        end = (
            sorted_leaders[block_id + 1] - 1
            if block_id + 1 < len(sorted_leaders)
            else len(instructions) - 1
        )
        block_instructions = instructions[start : end + 1]
        blocks.append(
            BasicBlock(
                block_id=block_id,
                start_index=start,
                end_index=end,
                instructions=list(block_instructions),
                successors=set(),
                predecessors=set(),
            )
        )
        for idx in range(start, end + 1):
            index_to_block[idx] = block_id

    label_to_block: dict[str, int] = {}
    for block in blocks:
        for ins in block.instructions:
            if ins.op == "label" and isinstance(ins.result, str):
                label_to_block[ins.result] = block.block_id

    for i, block in enumerate(blocks):
        if not block.instructions:
            continue
        last = block.instructions[-1]
        if last.op == "goto" and isinstance(last.result, str):
            target = label_to_block.get(last.result)
            if target is not None:
                block.successors.add(target)
        elif last.op in {"ifz", "ifnz"} and isinstance(last.result, str):
            target = label_to_block.get(last.result)
            if target is not None:
                block.successors.add(target)
            if i + 1 < len(blocks):
                block.successors.add(blocks[i + 1].block_id)
        elif last.op != "return":
            if i + 1 < len(blocks):
                block.successors.add(blocks[i + 1].block_id)

    id_to_block = {block.block_id: block for block in blocks}
    for block in blocks:
        for succ in block.successors:
            id_to_block[succ].predecessors.add(block.block_id)

    return CFG(function_name=function_name, blocks=blocks)


def _reachable_blocks(cfg: CFG) -> set[int]:
    if not cfg.blocks:
        return set()
    reachable: set[int] = set()
    stack = [cfg.blocks[0].block_id]
    while stack:
        current = stack.pop()
        if current in reachable:
            continue
        reachable.add(current)
        block = next(b for b in cfg.blocks if b.block_id == current)
        for succ in block.successors:
            if succ not in reachable:
                stack.append(succ)
    return reachable


def _filter_reachable(cfg: CFG, reachable: set[int]) -> CFG:
    blocks = [b for b in cfg.blocks if b.block_id in reachable]
    old_to_new = {block.block_id: idx for idx, block in enumerate(blocks)}
    normalized: list[BasicBlock] = []
    for idx, block in enumerate(blocks):
        successors = {old_to_new[s] for s in block.successors if s in old_to_new}
        predecessors = {old_to_new[p] for p in block.predecessors if p in old_to_new}
        normalized.append(
            BasicBlock(
                block_id=idx,
                start_index=block.start_index,
                end_index=block.end_index,
                instructions=list(block.instructions),
                successors=successors,
                predecessors=predecessors,
            )
        )
    return CFG(function_name=cfg.function_name, blocks=normalized)


def _constant_propagation(cfg: CFG) -> list[BasicBlock]:
    in_env: dict[int, dict[str, str]] = {b.block_id: {} for b in cfg.blocks}
    out_env: dict[int, dict[str, str]] = {b.block_id: {} for b in cfg.blocks}

    changed = True
    while changed:
        changed = False
        for block in cfg.blocks:
            pred_envs = [out_env[p] for p in sorted(block.predecessors)]
            merged = _merge_envs(pred_envs)
            if merged != in_env[block.block_id]:
                in_env[block.block_id] = merged
                changed = True

            transformed, out = _transform_block(block.instructions, merged)
            if transformed != block.instructions:
                block.instructions = transformed
                changed = True
            if out != out_env[block.block_id]:
                out_env[block.block_id] = out
                changed = True
    return cfg.blocks


def _transform_block(
    instructions: list[Instruction], start_env: dict[str, str]
) -> tuple[list[Instruction], dict[str, str]]:
    env = dict(start_env)
    out: list[Instruction] = []

    for ins in instructions:
        cur = Instruction(op=ins.op, arg1=ins.arg1, arg2=ins.arg2, result=ins.result)
        _rewrite_instruction_operands(cur, env)

        if cur.op in BIN_OPS and _is_numeric_literal(cur.arg1) and _is_numeric_literal(cur.arg2):
            left = _parse_numeric(str(cur.arg1))
            right = _parse_numeric(str(cur.arg2))
            value = _eval_binop(cur.op, left, right)
            if value is not None:
                cur = Instruction(op="copy", arg1=str(value), result=cur.result)

        if cur.op == "neg" and _is_numeric_literal(cur.arg1):
            cur = Instruction(op="copy", arg1=str(-_parse_numeric(str(cur.arg1))), result=cur.result)

        out.append(cur)
        _update_env(env, cur)

    return out, env


def _rewrite_instruction_operands(ins: Instruction, env: dict[str, str]) -> None:
    if ins.op in {"copy", "neg", "ifz", "ifnz", "print", "param", "return"}:
        ins.arg1 = _rewrite_operand(ins.arg1, env)
    elif ins.op in BIN_OPS:
        ins.arg1 = _rewrite_operand(ins.arg1, env)
        ins.arg2 = _rewrite_operand(ins.arg2, env)


def _update_env(env: dict[str, str], ins: Instruction) -> None:
    if ins.op == "copy" and isinstance(ins.result, str):
        if _is_numeric_literal(ins.arg1):
            env[ins.result] = str(ins.arg1)
        else:
            env.pop(ins.result, None)
        return
    if ins.op in DEF_OPS and isinstance(ins.result, str):
        env.pop(ins.result, None)
        return
    if ins.op == "call" and isinstance(ins.result, str):
        env.pop(ins.result, None)


def _rewrite_operand(value: object | None, env: dict[str, str]) -> object | None:
    if isinstance(value, str) and _is_variable(value) and value in env:
        return env[value]
    return value


def _merge_envs(envs: list[dict[str, str]]) -> dict[str, str]:
    if not envs:
        return {}
    keys = set(envs[0].keys())
    for env in envs[1:]:
        keys &= set(env.keys())
    merged: dict[str, str] = {}
    for key in keys:
        values = {env[key] for env in envs}
        if len(values) == 1:
            merged[key] = next(iter(values))
    return merged


def _dead_store_elimination(cfg: CFG) -> list[BasicBlock]:
    use: dict[int, set[str]] = {}
    defs: dict[int, set[str]] = {}
    for block in cfg.blocks:
        u, d = _compute_use_def(block.instructions)
        use[block.block_id] = u
        defs[block.block_id] = d

    live_in: dict[int, set[str]] = {b.block_id: set() for b in cfg.blocks}
    live_out: dict[int, set[str]] = {b.block_id: set() for b in cfg.blocks}

    changed = True
    while changed:
        changed = False
        for block in reversed(cfg.blocks):
            out = set()
            for succ in block.successors:
                out |= live_in[succ]
            inp = use[block.block_id] | (out - defs[block.block_id])
            if out != live_out[block.block_id]:
                live_out[block.block_id] = out
                changed = True
            if inp != live_in[block.block_id]:
                live_in[block.block_id] = inp
                changed = True

    for block in cfg.blocks:
        live = set(live_out[block.block_id])
        kept: list[Instruction] = []
        for ins in reversed(block.instructions):
            def_var = _def_var(ins)
            uses = _use_vars(ins)
            removable = ins.op in DEF_OPS and def_var is not None
            if removable and def_var not in live:
                continue
            kept.append(ins)
            if def_var is not None:
                live.discard(def_var)
            live |= uses
        kept.reverse()
        block.instructions = kept
    return cfg.blocks


def _local_cse(cfg: CFG) -> list[BasicBlock]:
    commutative = {"add", "mul", "eq", "ne"}
    for block in cfg.blocks:
        expr_to_var: dict[tuple[object, ...], str] = {}
        kept: list[Instruction] = []
        for ins in block.instructions:
            cur = Instruction(op=ins.op, arg1=ins.arg1, arg2=ins.arg2, result=ins.result)
            def_var = _def_var(cur)
            if cur.op in BIN_OPS and isinstance(cur.result, str):
                a = cur.arg1
                b = cur.arg2
                if cur.op in commutative and str(a) > str(b):
                    a, b = b, a
                key = ("bin", cur.op, a, b)
                if key in expr_to_var:
                    cur = Instruction(op="copy", arg1=expr_to_var[key], result=cur.result)
                else:
                    expr_to_var[key] = cur.result
            elif cur.op == "neg" and isinstance(cur.result, str):
                key = ("neg", cur.arg1)
                if key in expr_to_var:
                    cur = Instruction(op="copy", arg1=expr_to_var[key], result=cur.result)
                else:
                    expr_to_var[key] = cur.result

            if def_var is not None:
                expr_to_var = {
                    k: v
                    for k, v in expr_to_var.items()
                    if v != def_var and not _expr_uses_var(k, def_var)
                }
            kept.append(cur)
        block.instructions = kept
    return cfg.blocks


def _loop_invariant_code_motion(cfg: CFG) -> list[BasicBlock]:
    if len(cfg.blocks) < 2:
        return cfg.blocks

    for tail in cfg.blocks:
        for succ in sorted(tail.successors):
            if succ >= tail.block_id:
                continue
            header_id = succ
            loop_ids = set(range(header_id, tail.block_id + 1))
            preheader_id = header_id - 1
            if preheader_id < 0 or preheader_id in loop_ids:
                continue
            preheader = cfg.blocks[preheader_id]
            loop_blocks = [cfg.blocks[i] for i in sorted(loop_ids)]

            assigned: set[str] = set()
            for block in loop_blocks:
                for ins in block.instructions:
                    d = _def_var(ins)
                    if d is not None:
                        assigned.add(d)

            moved: list[Instruction] = []
            for block in loop_blocks:
                kept: list[Instruction] = []
                for ins in block.instructions:
                    d = _def_var(ins)
                    if (
                        d is not None
                        and ins.op in DEF_OPS
                        and _is_loop_invariant(ins, assigned)
                        and _appears_before_jump(ins, block.instructions)
                    ):
                        moved.append(ins)
                    else:
                        kept.append(ins)
                block.instructions = kept

            if moved:
                insert_at = len(preheader.instructions)
                if preheader.instructions and preheader.instructions[-1].op in JUMP_OPS | {"return"}:
                    insert_at -= 1
                preheader.instructions[insert_at:insert_at] = moved
    return cfg.blocks


def _compute_use_def(instructions: list[Instruction]) -> tuple[set[str], set[str]]:
    use: set[str] = set()
    defs: set[str] = set()
    for ins in instructions:
        for var in _use_vars(ins):
            if var not in defs:
                use.add(var)
        def_var = _def_var(ins)
        if def_var is not None:
            defs.add(def_var)
    return use, defs


def _use_vars(ins: Instruction) -> set[str]:
    values: list[object] = []
    if ins.op in BIN_OPS:
        values = [ins.arg1, ins.arg2]
    elif ins.op in {"copy", "neg", "ifz", "ifnz", "print", "param", "return"}:
        values = [ins.arg1]
    out: set[str] = set()
    for value in values:
        if isinstance(value, str) and _is_variable(value):
            out.add(value)
    return out


def _def_var(ins: Instruction) -> str | None:
    if ins.op in DEF_OPS and isinstance(ins.result, str):
        return ins.result
    if ins.op == "call" and isinstance(ins.result, str):
        return ins.result
    return None


def _expr_uses_var(key: tuple[object, ...], var: str) -> bool:
    for item in key:
        if isinstance(item, str) and item == var:
            return True
    return False


def _is_loop_invariant(ins: Instruction, assigned: set[str]) -> bool:
    if ins.op not in DEF_OPS:
        return False
    for v in _use_vars(ins):
        if v in assigned:
            return False
    return True


def _appears_before_jump(ins: Instruction, instructions: list[Instruction]) -> bool:
    for cur in instructions:
        if cur is ins:
            return True
        if cur.op in JUMP_OPS | {"return"}:
            return False
    return True


def _flatten_cfg(cfg: CFG) -> list[Instruction]:
    flat: list[Instruction] = []
    for block in cfg.blocks:
        flat.extend(block.instructions)
    return flat


def _is_variable(value: str) -> bool:
    if _is_numeric_literal(value):
        return False
    if value.startswith('"') and value.endswith('"'):
        return False
    return value.replace("_", "").isalnum() and not value[0].isdigit()


def _is_numeric_literal(value: object | None) -> bool:
    if not isinstance(value, str):
        return False
    if value.startswith("-"):
        value = value[1:]
    if value.count(".") > 1:
        return False
    if "." in value:
        left, right = value.split(".", 1)
        return (left.isdigit() or left == "") and right.isdigit()
    return value.isdigit()


def _parse_numeric(value: str) -> int | float:
    if "." in value:
        return float(value)
    return int(value)


def _eval_binop(op: str, left: int | float, right: int | float) -> int | float | None:
    if op == "add":
        return left + right
    if op == "sub":
        return left - right
    if op == "mul":
        return left * right
    if op == "div":
        if float(right) == 0:
            return None
        if isinstance(left, float) or isinstance(right, float):
            return left / right
        return int(left) // int(right)
    if op == "lt":
        return 1 if left < right else 0
    if op == "le":
        return 1 if left <= right else 0
    if op == "gt":
        return 1 if left > right else 0
    if op == "ge":
        return 1 if left >= right else 0
    if op == "eq":
        return 1 if left == right else 0
    if op == "ne":
        return 1 if left != right else 0
    return None
