from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from patakha.compiler import compile_source, format_ast_dot, format_cfg_dot
from patakha.diagnostics import PatakhaAggregateError, PatakhaError
from patakha.formatter import format_source
from patakha.lint import lint_source
from patakha.ll1 import build_ll1_artifacts
from patakha.slr_lab import build_demo_slr


class CompilerTests(unittest.TestCase):
    def test_typed_functions_and_loops_compile(self) -> None:
        source = """
kaam bhai add(bhai a, bhai b) {
    nikal max(a, b);
}
shuru
bhai i = 0;
bhai s = 0;
jabtak (i = 0; i < 5; i = i + 1) {
    agar (i == 2) { jari; }
    s = s + i;
}
kar {
    s = s - 1;
} tabtak (s > 3);
bol(add(s, 10));
nikal 0;
bass
""".strip()
        result = compile_source(source)
        self.assertIn("int add(int a, int b)", result.c_code)
        self.assertIn("for (", result.c_code)
        self.assertIn("do {", result.c_code)
        self.assertIn("continue;", result.c_code)

    def test_semicolon_optional_and_increment_ops(self) -> None:
        source = """
shuru
bhai i = 0
bhai sum = 0
++i
i++
i += 2
jabtak (i = 0; i < 4; ++i) {
    sum += i
}
bol(sum)
nikal 0
bass
""".strip()
        result = compile_source(source)
        self.assertIn("i = (i + 1);", result.c_code)
        self.assertIn("i = (i + 2);", result.c_code)
        self.assertIn("for (", result.c_code)

    def test_struct_and_class_fields(self) -> None:
        source = """
struct User {
    bhai age;
    text name;
};
kaksha Box {
    bhai w;
    bhai h;
};
shuru
struct User u;
kaksha Box b;
u.age = 21;
b.w = 3;
b.h = 4;
bol(u.age);
nikal 0;
bass
""".strip()
        result = compile_source(source)
        self.assertIn("typedef struct User", result.c_code)
        self.assertIn("typedef struct Box", result.c_code)
        self.assertIn("u.age = 21;", result.c_code)
        self.assertIn("b.w = 3;", result.c_code)

    def test_float_and_cast_compile(self) -> None:
        source = """
shuru
decimal x = 5.5;
bhai y = bhai(x + 2.0);
bol(x);
bol(y);
nikal 0;
bass
""".strip()
        result = compile_source(source)
        self.assertIn("double x = 5.5;", result.c_code)
        self.assertIn("int y = ((int)((x + 2.0)));", result.c_code)

    def test_import_multi_file_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib = root / "lib.bhai"
            main = root / "main.bhai"
            lib.write_text(
                """
kaam decimal twice(decimal x) {
    nikal decimal(x * 2.0);
}
shuru
bass
""".strip(),
                encoding="utf-8",
            )
            main.write_text(
                """
import "lib.bhai";
shuru
decimal a = 3.5;
bol(twice(a));
nikal 0;
bass
""".strip(),
                encoding="utf-8",
            )
            result = compile_source(main.read_text(encoding="utf-8"), source_name=main)
            self.assertIn("double twice(double x)", result.c_code)
            self.assertIn("printf(\"%g\\n\", twice(a));", result.c_code)

    def test_arrays_and_len_builtin(self) -> None:
        source = """
shuru
bhai arr[4];
arr[0] = 1;
arr[1] = 2;
arr[2] = 3;
arr[3] = 4;
bol(len(arr));
nikal 0;
bass
""".strip()
        result = compile_source(source)
        self.assertIn("int arr[4];", result.c_code)
        self.assertIn("sizeof(arr)", result.c_code)

    def test_legacy_program_keywords_compile(self) -> None:
        source = """
start_bhai
bhai x = 1;
bol(x);
nikal 0;
bas_kar
""".strip()
        result = compile_source(source)
        self.assertIn("int main(void)", result.c_code)
        self.assertIn("printf", result.c_code)

    def test_switch_case_default_compile(self) -> None:
        source = """
shuru
bhai x = 2;
switch (x) {
    case 1:
        bol("one");
        tod;
    case 2:
        bol("two");
        tod;
    default:
        bol("other");
}
nikal 0;
bass
""".strip()
        result = compile_source(source)
        self.assertIn("switch (x)", result.c_code)
        self.assertIn("case 1:", result.c_code)
        self.assertIn("default:", result.c_code)
        self.assertIn("SWITCH_CASE", result.stack_code)

    def test_duplicate_case_error(self) -> None:
        source = """
shuru
bhai x = 2;
switch (x) {
    case 1:
        bol("one");
        tod;
    case 1:
        bol("again");
        tod;
}
nikal 0;
bass
""".strip()
        with self.assertRaises(PatakhaError) as ctx:
            compile_source(source)
        self.assertEqual(ctx.exception.code, "duplicate_case")

    def test_break_inside_switch_allowed(self) -> None:
        source = """
shuru
bhai x = 3;
switch (x) {
    case 3:
        bol("ok");
        tod;
    default:
        bol("no");
}
nikal 0;
bass
""".strip()
        result = compile_source(source)
        self.assertIn("break;", result.c_code)

    def test_stack_backend_generated(self) -> None:
        source = """
shuru
bhai x = 1;
bhai y = 2;
bol(x + y);
nikal 0;
bass
""".strip()
        result = compile_source(source)
        self.assertIn("FUNC __main__", result.stack_code)
        self.assertIn("ADD", result.stack_code)

    def test_formatter_outputs_canonical_program(self) -> None:
        source = """
shuru
bhai   x=1;
agar(x>0){
bol("ok");
}
nikal 0;
bass
""".strip()
        formatted = format_source(source)
        self.assertTrue(formatted.endswith("\n"))
        self.assertIn("agar ((x > 0)) {", formatted)
        recompiled = compile_source(formatted)
        self.assertIn("printf", recompiled.c_code)

    def test_lint_reports_legacy_keyword(self) -> None:
        source = """
start_bhai
bhai x = 1;
nikal 0;
bas_kar
""".strip()
        issues = lint_source(source)
        codes = {issue.code for issue in issues}
        self.assertIn("legacy_keyword", codes)

    def test_break_continue_outside_loop_error(self) -> None:
        source = """
shuru
tod;
bass
""".strip()
        with self.assertRaises(PatakhaError) as ctx:
            compile_source(source)
        self.assertEqual(ctx.exception.code, "break_outside_loop")

    def test_did_you_mean_variable_hint(self) -> None:
        source = """
shuru
bhai score = 10;
bol(scor);
nikal 0;
bass
""".strip()
        with self.assertRaises(PatakhaError) as ctx:
            compile_source(source)
        self.assertIn("Did you mean `score`?", ctx.exception.technical)

    def test_import_requires_source_context(self) -> None:
        source = """
import "lib.bhai";
shuru
nikal 0;
bass
""".strip()
        with self.assertRaises(PatakhaError) as ctx:
            compile_source(source)
        self.assertEqual(ctx.exception.code, "missing_import")

    def test_return_type_mismatch_error(self) -> None:
        source = """
kaam khali hello() {
    nikal 1;
}
shuru
nikal 0;
bass
""".strip()
        with self.assertRaises(PatakhaError) as ctx:
            compile_source(source)
        self.assertEqual(ctx.exception.code, "return_type")

    def test_warning_pipeline(self) -> None:
        source = """
shuru
bhai x = 10;
agar (sach) {
    nikal 0;
    bhai y = 99;
}
bass
""".strip()
        result = compile_source(source)
        codes = {w.code for w in result.semantic.warnings}
        self.assertIn("constant_condition", codes)
        self.assertIn("unreachable_code", codes)
        self.assertIn("unused_variable", codes)

    def test_dot_outputs(self) -> None:
        source = """
shuru
bhai x = 10;
bol(x);
nikal 0;
bass
""".strip()
        result = compile_source(source)
        ast_dot = format_ast_dot(result.ast)
        cfg_dot = format_cfg_dot(result.cfg_by_function)
        self.assertIn("digraph AST", ast_dot)
        self.assertIn("digraph CFG", cfg_dot)

    def test_parser_recovers_multiple_errors(self) -> None:
        source = """
shuru
bhai x = 10
bhai y = ;
agar (x > ) {
    bol("oops")
}
bass
""".strip()
        with self.assertRaises(PatakhaAggregateError) as ctx:
            compile_source(source)
        self.assertGreaterEqual(len(ctx.exception.errors), 2)

    def test_source_frame_in_error(self) -> None:
        source = """
shuru
bhai x =
bass
""".strip()
        with self.assertRaises(PatakhaAggregateError) as ctx:
            compile_source(source)
        pretty = ctx.exception.pretty("sample.bhai", source_text=source)
        self.assertIn("| bass", pretty)
        self.assertIn("^", pretty)

    def test_ll1_is_conflict_free(self) -> None:
        artifacts = build_ll1_artifacts()
        self.assertEqual(len(artifacts.conflicts), 0)

    def test_slr_demo_is_conflict_free(self) -> None:
        artifacts = build_demo_slr()
        self.assertEqual(len(artifacts.conflicts), 0)
        self.assertGreater(len(artifacts.states), 0)

    def test_fuzz_smoke_no_internal_crash(self) -> None:
        snippets = [
            "bhai x = 1;",
            "bool ok = sach;",
            "text t = \"hi\";",
            "x = x + 1;",
            "agar (x > 0) { bol(x); }",
            "tabtak (x < 5) { x = x + 1; }",
            "jabtak (x = 0; x < 3; x = x + 1) { bol(x); }",
            "kar { x = x - 1; } tabtak (x > 0);",
            "switch (x) { case 1: bol(1); tod; default: bol(0); }",
            "bol(max(x, 2));",
            "nikal 0;",
            "bhai z = ;",
            "agar (x > ) {",
            "foo();",
        ]
        for _ in range(20):
            body = "\n".join(random.choice(snippets) for _ in range(6))
            source = f"shuru\n{body}\nbass"
            try:
                compile_source(source)
            except (PatakhaError, PatakhaAggregateError):
                pass
            except Exception as exc:  # pragma: no cover
                self.fail(f"Unexpected internal crash: {type(exc).__name__} {exc}")


if __name__ == "__main__":
    unittest.main()
