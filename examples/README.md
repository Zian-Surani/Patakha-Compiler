# examples/

Sample Patakha programs (`.bhai`) plus generated artifacts.

## Key Sources

- `hello.bhai`: basic declarations, function call, arrays, struct fields.
- `loop.bhai`: `jabtak`, `kar ... tabtak`, `tod`, `jari`.
- `switch_demo.bhai`: `switch/case/default`.
- `advanced.bhai`: structs, classes (`kaksha`), typed functions, loops.
- `shadow.bhai`: scope shadowing behavior.
- `warn.bhai`: warning demonstrations.
- `semicolonless.bhai`: optional semicolons + `++`/`--`/`+=` sugar.
- `lib_math.bhai`: importable module with typed helper functions.
- `import_float_demo.bhai`: import + float + cast usage.

## Compile Examples

```bash
python -m patakha examples/hello.bhai --backend c --gcc
python -m patakha examples/loop.bhai --backend stack
```

## Generated Files

Depending on flags, these may appear next to a source file:

- `.c`, `.exe`
- `.stk`
- `.tokens.txt`
- `.raw.ir`, `.ir`
- `.ast.txt`, `.ast.dot`
- `.cfg.txt`, `.cfg.dot`
- `.symbols.txt`
- `.warnings.txt`
