# patakha/

Core compiler implementation.

## Main Modules

- `lexer.py`: tokenization and keyword/operator mapping.
- `parser.py`: AST parser with error recovery, optional semicolons, and assignment sugar (`+=`, `++`, etc.).
- `semantic.py`: type checks, scope checks, function/type validation, warnings.
- `ir.py`: intermediate representation generation.
- `optimizer.py`: CFG and optimization passes (constant propagation, DCE, peephole-style cleanup).
- `codegen_c.py`: C backend generation.
- `codegen_stack.py`: stack-machine backend generation.
- `compiler.py`: end-to-end compile pipeline orchestration.
- `cli.py`: `patakha` CLI (`compile`, `fmt`, `lint`, `repl`).
- `interpreter.py`: tree-walk interpreter runtime used by REPL.
- `formatter.py`: canonical source formatter.
- `lint.py`: static lint checks and style warnings.
- `diagnostics.py`: error/warning formatting and nag-line messages.
- `studio.py`: Patakha Studio desktop GUI.
- `vscode_runner.py`: helper entrypoint for VS Code Run/Debug.
- `ll1.py` and `slr_lab.py`: grammar artifacts for coursework/lab outputs.

## Entry Points

- Package CLI: `python -m patakha ...`
- GUI: `python -m patakha.studio`

## Design Notes

- AST node definitions are in `ast_nodes.py`.
- Token model is in `token.py`.
- `__main__.py` forwards to CLI main.
