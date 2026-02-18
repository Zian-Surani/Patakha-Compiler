# tests/

Unit tests for compiler correctness and stability.

## Scope

- Parsing and semantic checks
- Typed functions and control flow
- Struct/class field handling
- Stack backend and C backend smoke checks
- Formatter/linter behavior
- LL(1)/SLR artifact sanity checks
- Parser recovery and diagnostic formatting
- Fuzz-like smoke test for crash resistance

## Run

```bash
python -m unittest discover -s tests -v
```
