# Patakha Compiler

Patakha is a Python-built compiler for a Hinglish-flavored language (`.bhai`) with:

- Lexer, parser, semantic analysis
- Intermediate representation + optimization
- Multi-file module imports
- C code generation (`.c`) + optional executable via `gcc`
- Stack backend generation (`.stk`)
- CLI tools (`compile`, `fmt`, `lint`, `repl`)
- A desktop GUI (`Patakha Studio`)
- VS Code integration (tasks, launch profiles, local language extension)

## Quick Start

### Requirements

- Python `>=3.10`
- `gcc` in `PATH` (only if you want executable generation)

### Compile a program

```bash
python -m patakha examples/hello.bhai --backend c
```

### Compile and run via gcc

```bash
python -m patakha examples/hello.bhai --backend c --gcc
```

### Generate stack backend code

```bash
python -m patakha examples/hello.bhai --backend stack
```

### Format and lint

```bash
python -m patakha fmt examples/hello.bhai -w
python -m patakha lint examples/hello.bhai --strict
```

## Language Summary

### Core keywords

| Category | Keywords |
| --- | --- |
| Program | `shuru`, `bass` |
| Types | `bhai`, `decimal`, `bool`, `text`, `khali` |
| Control | `agar`, `warna`, `tabtak`, `jabtak`, `kar`, `switch`, `case`, `default`, `tod`, `jari` |
| Functions | `kaam`, `nikal` |
| Data types | `struct`, `kaksha` |
| Output/Input | `bol`, `bata` |
| Modules | `import` |

### Useful aliases (backward compatible)

- `start_bhai -> shuru`
- `bas_kar -> bass`
- `laao -> import`
- `while -> tabtak`
- `for -> jabtak`
- `do -> kar`
- `break -> tod`
- `continue -> jari`
- `class -> kaksha`
- `void -> khali`
- `float -> decimal`
- `input() -> bata()`

### Statement support

- Variable declarations (`bhai`, `bool`, `text`, user-defined types)
- Float support (`decimal`) and explicit casts: `bhai(x)`, `decimal(x)`, `bool(x)`
- Assignments to variable / array element / field
- Expression statements
- `agar/warna`
- `tabtak` (while)
- `jabtak` (for)
- `kar ... tabtak` (do-while)
- `switch/case/default`
- `tod` / `jari`
- `bol(...)` print
- `nikal ...` return
- Typed functions via `kaam`

### Operators

- Arithmetic: `+ - * / %`
- Relational: `< <= > >= == !=`
- Logical: `&& || !`
- Assignment family: `= += -= *= /= %=`
- Increment/decrement in statements and loop clauses: `i++`, `++i`, `i--`, `--i`
- Module imports: `import "lib_math.bhai"`

### Semicolon policy

- End-of-statement semicolons are optional in most places.
- In `jabtak(init; condition; post)` headers, the two separators remain mandatory.

## Example Program

```bhai
struct User {
    bhai age
    text name
}

kaam bhai add(bhai a, bhai b) {
    nikal max(a, b)
}

shuru
bhai i = 0
bhai sum = 0

jabtak (i = 0; i < 5; ++i) {
    sum += i
}

agar (sum > 5) {
    bol("Full power")
} warna {
    bol("Thoda aur")
}

nikal 0
bass
```

## Compiler Pipeline

1. **Lexing** (`patakha/lexer.py`)
2. **Parsing to AST** (`patakha/parser.py`, `patakha/ast_nodes.py`)
3. **Semantic analysis** (`patakha/semantic.py`)
4. **IR generation** (`patakha/ir.py`)
5. **Optimization / CFG** (`patakha/optimizer.py`)
   - constant propagation + dead-store elimination
   - local common subexpression elimination (CSE)
   - loop-invariant code motion (LICM, conservative)
6. **Backend codegen**:
   - C backend (`patakha/codegen_c.py`)
   - Stack backend (`patakha/codegen_stack.py`)

Optional dumps expose tokens, AST, symbols, IR, CFG, LL(1), SLR artifacts.

## CLI Reference

### Compile

```bash
python -m patakha <source.bhai> [--backend c|stack] [--gcc]
```

Useful flags:

- `--emit-warnings`
- `--emit-tokens`
- `--emit-raw-ir`
- `--emit-ir`
- `--emit-stack`
- `--dump-ast`
- `--dump-ast-dot`
- `--dump-symbols`
- `--dump-cfg`
- `--dump-cfg-dot`
- `--dump-ll1`
- `--dump-slr`

### Format

```bash
python -m patakha fmt <source.bhai> -w
python -m patakha fmt <source.bhai> --check
```

### Lint

```bash
python -m patakha lint <source.bhai>
python -m patakha lint <source.bhai> --strict
```

### REPL

```bash
python -m patakha repl
```

## Patakha Studio (GUI)

Launch:

```bash
python -m patakha.studio
```

or on Windows:

```bash
launch_studio.bat
```

Features:

- Open/save `.bhai` files
- Compile C / compile stack / compile+run
- Syntax highlighting
- Auto indentation on Enter
- Auto bracket/quote pairing
- Pair-aware backspace
- Live line highlighting for parser/semantic errors and warnings
- Output panes for diagnostics, generated C, generated stack code
- Debug trace tab with tokens, AST, raw IR, optimized IR, CFG

## VS Code Integration

### Built-in tasks

Press `Ctrl+Shift+B` and choose:

- `Patakha: Run current file (C backend)`
- `Patakha: Build current file (stack backend)`
- `Patakha: Full diagnostics (current file)`
- `Patakha: Format current file`
- `Patakha: Lint current file`
- `Patakha: Install Patakha Color Extension`

### Run & Debug

- Launch profile: `Patakha: Run active .bhai (compile + execute)`

### Local syntax extension

Install locally:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_patakha_extension.ps1 -Force
```

Extension source: `tools/vscode-patakha-language`

## Import / Multi-file Usage

`lib_math.bhai`:

```bhai
kaam decimal avg(decimal a, decimal b) {
    nikal decimal((a + b) / 2.0)
}
shuru
bass
```

`main.bhai`:

```bhai
import "lib_math.bhai"
shuru
decimal x = 10.0
bol(avg(x, 4.0))
nikal 0
bass
```

Compile:

```bash
python -m patakha main.bhai --backend c --gcc
```

## Windows Packaging

One-click Windows executable bundle:

```powershell
pip install pyinstaller
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_windows_release.ps1 -OneFile
```

or:

```bat
build_release.bat
```

Optional installer build:
- Install Inno Setup (`iscc` in PATH)
- Script auto-generates `Patakha-Setup.exe` via `tools/patakha_installer.iss`

## Project Layout

- `patakha/` compiler source modules
- `examples/` sample `.bhai` programs and generated artifacts
- `tests/` unit tests
- `tools/` VS Code extension and utility scripts
- `.vscode/` workspace tasks, launch configs, settings
- `.github/` CI workflow

Each top-level folder includes its own `README.md` for local details.

## Development

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Notes

- Diagnostics include technical errors plus desi nagging messages.
- Legacy keywords are still accepted to avoid breaking old files.
- Parser recovery supports multiple syntax errors in one pass.
