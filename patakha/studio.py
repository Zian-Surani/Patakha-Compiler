from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from patakha.compiler import compile_source, format_ast, format_cfg, format_ir, format_tokens
from patakha.diagnostics import PatakhaAggregateError, PatakhaError, PatakhaWarning
from patakha.lexer import Lexer
from patakha.parser import Parser
from patakha.semantic import SemanticAnalyzer


APP_TITLE = "Patakha Studio"

KEYWORDS = {
    "import",
    "laao",
    "shuru",
    "bass",
    "start_bhai",
    "bas_kar",
    "kaam",
    "agar",
    "warna",
    "jabtak",
    "tabtak",
    "while",
    "for",
    "kar",
    "do",
    "switch",
    "case",
    "default",
    "tod",
    "break",
    "jari",
    "continue",
    "nikal",
    "bol",
}
TYPES = {"bhai", "bool", "text", "khali", "void", "struct", "kaksha", "class"}
TYPES = TYPES | {"decimal", "float"}
BUILTINS = {"max", "len", "bata", "input", "sach", "jhooth"}
OPEN_CLOSE_PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}


class PatakhaStudio(tk.Tk):
    def __init__(self, initial_file: Path | None = None) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1220x800")
        self.minsize(980, 640)

        self.current_file: Path | None = None
        self.dirty = False
        self._highlight_job: str | None = None
        self._diagnostics_job: str | None = None

        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_exit)

        if initial_file is not None:
            self._open_from_path(initial_file)
        else:
            self._refresh_title()
            self._set_status("Ready")
            self._schedule_highlight()
            self._schedule_diagnostics()

    def _build_ui(self) -> None:
        self._configure_theme()
        self._build_menu()
        self._build_toolbar()

        pane = ttk.Panedwindow(self, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        editor_frame = ttk.Frame(pane)
        bottom_frame = ttk.Frame(pane)
        pane.add(editor_frame, weight=7)
        pane.add(bottom_frame, weight=3)

        ttk.Label(editor_frame, text="Patakha Source").pack(anchor=tk.W)
        self.editor = ScrolledText(
            editor_frame,
            wrap=tk.NONE,
            undo=True,
            font=("Consolas", 12),
            background="#121417",
            foreground="#E8EAF0",
            insertbackground="#E8EAF0",
            selectbackground="#2E436E",
            padx=8,
            pady=8,
        )
        self.editor.pack(fill=tk.BOTH, expand=True)
        self._configure_editor_tags()
        self.editor.bind("<<Modified>>", self._on_modified)
        self.editor.bind("<KeyRelease>", self._schedule_highlight)
        self.editor.bind("<ButtonRelease>", self._schedule_highlight)
        self.editor.bind("<<Paste>>", self._schedule_highlight)
        self.editor.bind("<KeyRelease>", self._schedule_diagnostics, add="+")
        self.editor.bind("<ButtonRelease>", self._schedule_diagnostics, add="+")
        self.editor.bind("<<Paste>>", self._schedule_diagnostics, add="+")
        self.editor.bind("<Return>", self._on_return_pressed)
        self.editor.bind("<Tab>", self._on_tab_pressed)
        self.editor.bind("<KeyPress>", self._on_key_press)
        self.editor.bind("<BackSpace>", self._on_backspace)

        notebook = ttk.Notebook(bottom_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        output_tab = ttk.Frame(notebook)
        c_tab = ttk.Frame(notebook)
        stack_tab = ttk.Frame(notebook)
        debug_tab = ttk.Frame(notebook)
        notebook.add(output_tab, text="Run Output")
        notebook.add(c_tab, text="Generated C")
        notebook.add(stack_tab, text="Stack Code")
        notebook.add(debug_tab, text="Debug Trace")

        self.output = ScrolledText(
            output_tab,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 11),
        )
        self.output.pack(fill=tk.BOTH, expand=True)

        self.c_code_view = ScrolledText(
            c_tab,
            wrap=tk.NONE,
            state=tk.DISABLED,
            font=("Consolas", 11),
        )
        self.c_code_view.pack(fill=tk.BOTH, expand=True)

        self.stack_code_view = ScrolledText(
            stack_tab,
            wrap=tk.NONE,
            state=tk.DISABLED,
            font=("Consolas", 11),
        )
        self.stack_code_view.pack(fill=tk.BOTH, expand=True)

        self.debug_view = ScrolledText(
            debug_tab,
            wrap=tk.NONE,
            state=tk.DISABLED,
            font=("Consolas", 11),
        )
        self.debug_view.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="")
        status = ttk.Label(self, textvariable=self.status_var, anchor=tk.W)
        status.pack(fill=tk.X, padx=8, pady=(0, 8))

    def _configure_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    def _configure_editor_tags(self) -> None:
        self.editor.tag_configure("keyword", foreground="#57C7FF")
        self.editor.tag_configure("type", foreground="#C586C0")
        self.editor.tag_configure("builtin", foreground="#F2C66D")
        self.editor.tag_configure("number", foreground="#B5CEA8")
        self.editor.tag_configure("string", foreground="#CE9178")
        self.editor.tag_configure("comment", foreground="#6A9955")
        self.editor.tag_configure("function", foreground="#DCDCAA")
        self.editor.tag_configure("warning_line", background="#3C3018")
        self.editor.tag_configure("error_line", background="#402126")
        self.editor.tag_lower("warning_line")
        self.editor.tag_lower("error_line")

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self._new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="Open...", command=self._open_file, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self._save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self._save_file_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        build_menu = tk.Menu(menubar, tearoff=0)
        build_menu.add_command(label="Compile C", command=self._compile_c, accelerator="F5")
        build_menu.add_command(label="Compile Stack", command=self._compile_stack, accelerator="F6")
        build_menu.add_command(label="Compile + Run (C)", command=self._run_c, accelerator="F9")
        menubar.add_cascade(label="Build", menu=build_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Clear Output", command=self._clear_output)
        menubar.add_cascade(label="View", menu=view_menu)

        self.config(menu=menubar)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=8)

        ttk.Button(bar, text="New", command=self._new_file).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="Open", command=self._open_file).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="Save", command=self._save_file).pack(side=tk.LEFT, padx=(0, 14))
        ttk.Button(bar, text="Compile C", command=self._compile_c).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="Compile Stack", command=self._compile_stack).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="Run C", command=self._run_c).pack(side=tk.LEFT, padx=(0, 6))
        self.debug_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Debug Trace", variable=self.debug_var).pack(side=tk.LEFT, padx=(8, 6))
        ttk.Button(bar, text="Clear Output", command=self._clear_output).pack(side=tk.LEFT)

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-n>", lambda _e: self._new_file())
        self.bind("<Control-o>", lambda _e: self._open_file())
        self.bind("<Control-s>", lambda _e: self._save_file())
        self.bind("<Control-Shift-S>", lambda _e: self._save_file_as())
        self.bind("<Control-q>", lambda _e: self._on_exit())
        self.bind("<F5>", lambda _e: self._compile_c())
        self.bind("<F6>", lambda _e: self._compile_stack())
        self.bind("<F9>", lambda _e: self._run_c())

    def _on_modified(self, _event: object) -> None:
        if self.editor.edit_modified():
            self.dirty = True
            self._refresh_title()
            self.editor.edit_modified(False)
            self._schedule_highlight()
            self._schedule_diagnostics()

    def _new_file(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        self.current_file = None
        self.editor.delete("1.0", tk.END)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self.dirty = False
        self._refresh_title()
        self._set_status("New file")
        self._schedule_highlight()
        self._schedule_diagnostics()

    def _open_file(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        chosen = filedialog.askopenfilename(
            title="Open Patakha file",
            filetypes=[
                ("Patakha files", "*.bhai"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not chosen:
            return
        self._open_from_path(Path(chosen))

    def _open_from_path(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not open file:\n{exc}")
            return
        self.current_file = path
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", text)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self.dirty = False
        self._refresh_title()
        self._set_status(f"Opened: {path}")
        self._schedule_highlight()
        self._schedule_diagnostics()

    def _save_file(self) -> bool:
        if self.current_file is None:
            return self._save_file_as()
        return self._write_to_file(self.current_file)

    def _save_file_as(self) -> bool:
        chosen = filedialog.asksaveasfilename(
            title="Save Patakha file",
            defaultextension=".bhai",
            filetypes=[
                ("Patakha files", "*.bhai"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not chosen:
            return False
        path = Path(chosen)
        if not self._write_to_file(path):
            return False
        self.current_file = path
        self._refresh_title()
        return True

    def _write_to_file(self, path: Path) -> bool:
        try:
            path.write_text(self._source_text(), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not save file:\n{exc}")
            return False
        self.dirty = False
        self.editor.edit_modified(False)
        self._refresh_title()
        self._set_status(f"Saved: {path}")
        return True

    def _compile_c(self) -> None:
        self._compile_backend("c")

    def _compile_stack(self) -> None:
        self._compile_backend("stack")

    def _compile_backend(self, backend: str) -> None:
        source_text = self._source_text()
        base_path = self._base_path_for_build(source_text)

        self._clear_output()
        self._append_output(f"[build] backend={backend}\n")
        try:
            result = compile_source(source_text, optimize=True, source_name=base_path)
        except PatakhaAggregateError as exc:
            self._append_output(exc.pretty(str(base_path), source_text=source_text) + "\n")
            self._set_status("Compilation failed")
            return
        except PatakhaError as exc:
            self._append_output(exc.pretty(str(base_path), source_text=source_text) + "\n")
            self._set_status("Compilation failed")
            return

        self._set_text(self.c_code_view, result.c_code)
        self._set_text(self.stack_code_view, result.stack_code)
        if self.debug_var.get():
            self._set_debug_trace(result)
        else:
            self._set_text(self.debug_view, "")

        if backend == "c":
            out_path = base_path.with_suffix(".c")
            out_path.write_text(result.c_code, encoding="utf-8")
            self._append_output(f"[ok] C code generated: {out_path}\n")
        else:
            out_path = base_path.with_suffix(".stk")
            out_path.write_text(result.stack_code, encoding="utf-8")
            self._append_output(f"[ok] Stack code generated: {out_path}\n")

        if result.semantic.warnings:
            self._append_output("\n[warning] Semantic warnings\n")
            for warning in result.semantic.warnings:
                self._append_output(f"  {warning.pretty(str(base_path))}\n")

        self._set_status(f"Compiled ({backend})")

    def _run_c(self) -> None:
        source_text = self._source_text()
        base_path = self._base_path_for_build(source_text)
        c_path = base_path.with_suffix(".c")
        exe_path = _executable_path(base_path)

        self._clear_output()
        self._append_output("[run] Compile + execute (C backend)\n")
        try:
            result = compile_source(source_text, optimize=True, source_name=base_path)
        except PatakhaAggregateError as exc:
            self._append_output(exc.pretty(str(base_path), source_text=source_text) + "\n")
            self._set_status("Compilation failed")
            return
        except PatakhaError as exc:
            self._append_output(exc.pretty(str(base_path), source_text=source_text) + "\n")
            self._set_status("Compilation failed")
            return

        self._set_text(self.c_code_view, result.c_code)
        self._set_text(self.stack_code_view, result.stack_code)
        if self.debug_var.get():
            self._set_debug_trace(result)
        else:
            self._set_text(self.debug_view, "")
        c_path.write_text(result.c_code, encoding="utf-8")
        self._append_output(f"[ok] C code generated: {c_path}\n")

        try:
            gcc = subprocess.run(
                ["gcc", str(c_path), "-o", str(exe_path)],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self._append_output("[error] `gcc` not found in PATH.\n")
            self._set_status("gcc not found")
            return

        if gcc.returncode != 0:
            self._append_output("[error] gcc compilation failed.\n")
            if gcc.stdout:
                self._append_output(gcc.stdout + "\n")
            if gcc.stderr:
                self._append_output(gcc.stderr + "\n")
            self._set_status("gcc failed")
            return

        self._append_output(f"[ok] Executable generated: {exe_path}\n")

        try:
            proc = subprocess.run(
                [str(exe_path)],
                capture_output=True,
                text=True,
                input="",
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self._append_output("[error] Program timed out while running.\n")
            self._set_status("Run timed out")
            return

        self._append_output("\n[program stdout]\n")
        self._append_output((proc.stdout or "<empty>") + ("\n" if not (proc.stdout or "").endswith("\n") else ""))
        if proc.stderr:
            self._append_output("\n[program stderr]\n")
            self._append_output(proc.stderr + ("\n" if not proc.stderr.endswith("\n") else ""))
        self._append_output(f"\n[exit code] {proc.returncode}\n")

        if result.semantic.warnings:
            self._append_output("\n[warning] Semantic warnings\n")
            for warning in result.semantic.warnings:
                self._append_output(f"  {warning.pretty(str(base_path))}\n")

        self._set_status("Run completed")

    def _source_text(self) -> str:
        return self.editor.get("1.0", "end-1c")

    def _base_path_for_build(self, source_text: str) -> Path:
        if self.current_file is not None:
            return self.current_file
        scratch = Path.cwd() / "studio_scratch.bhai"
        scratch.write_text(source_text, encoding="utf-8")
        return scratch

    def _append_output(self, text: str) -> None:
        self.output.configure(state=tk.NORMAL)
        self.output.insert(tk.END, text)
        self.output.see(tk.END)
        self.output.configure(state=tk.DISABLED)

    def _set_text(self, widget: ScrolledText, text: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state=tk.DISABLED)

    def _set_debug_trace(self, result: object) -> None:
        try:
            trace_parts = [
                "=== TOKENS ===",
                format_tokens(result.tokens),  # type: ignore[attr-defined]
                "",
                "=== AST ===",
                format_ast(result.ast),  # type: ignore[attr-defined]
                "",
                "=== IR (RAW) ===",
                format_ir(result.ir_raw),  # type: ignore[attr-defined]
                "",
                "=== IR (OPTIMIZED) ===",
                format_ir(result.ir_optimized),  # type: ignore[attr-defined]
                "",
                "=== CFG ===",
                format_cfg(result.cfg_by_function),  # type: ignore[attr-defined]
            ]
            self._set_text(self.debug_view, "\n".join(trace_parts))
        except Exception as exc:
            self._set_text(self.debug_view, f"[debug-trace-error] {exc}\n")

    def _clear_output(self) -> None:
        self._set_text(self.output, "")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _refresh_title(self) -> None:
        mark = "*" if self.dirty else ""
        file_part = str(self.current_file) if self.current_file is not None else "Untitled.bhai"
        self.title(f"{APP_TITLE} - {file_part}{mark}")

    def _confirm_discard_if_dirty(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            APP_TITLE,
            "You have unsaved changes.\nSave before continuing?",
        )
        if answer is None:
            return False
        if answer:
            return self._save_file()
        return True

    def _on_exit(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        self.destroy()

    def _schedule_highlight(self, _event: object | None = None) -> None:
        if self._highlight_job is not None:
            self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(80, self._apply_highlight)

    def _schedule_diagnostics(self, _event: object | None = None) -> None:
        if self._diagnostics_job is not None:
            self.after_cancel(self._diagnostics_job)
        self._diagnostics_job = self.after(220, self._apply_diagnostics)

    def _apply_highlight(self) -> None:
        self._highlight_job = None
        text = self._source_text()
        for tag in ("keyword", "type", "builtin", "number", "string", "comment", "function"):
            self.editor.tag_remove(tag, "1.0", tk.END)

        self._tag_regex(r"\b(?:%s)\b" % "|".join(re.escape(x) for x in sorted(KEYWORDS)), "keyword", text)
        self._tag_regex(r"\b(?:%s)\b" % "|".join(re.escape(x) for x in sorted(TYPES)), "type", text)
        self._tag_regex(r"\b(?:%s)\b" % "|".join(re.escape(x) for x in sorted(BUILTINS)), "builtin", text)
        self._tag_regex(r"\b\d+(?:\.\d+)?\b", "number", text)
        self._tag_regex(r'"(?:\\.|[^"\\])*"', "string", text)
        self._tag_regex(r"//.*?$|/\*[\s\S]*?\*/", "comment", text, flags=re.MULTILINE)
        self._tag_function_names(text)

        self.editor.tag_raise("comment")
        self.editor.tag_raise("string")

    def _apply_diagnostics(self) -> None:
        self._diagnostics_job = None
        text = self._source_text()
        self.editor.tag_remove("warning_line", "1.0", tk.END)
        self.editor.tag_remove("error_line", "1.0", tk.END)
        if not text.strip():
            return
        try:
            tokens = Lexer(text).tokenize()
            program = Parser(tokens).parse()
            semantic = SemanticAnalyzer().analyze(program)
        except PatakhaAggregateError as exc:
            self._tag_issue_lines(exc.errors, "error_line")
            return
        except PatakhaError as exc:
            self._tag_issue_lines([exc], "error_line")
            return
        except Exception:
            return
        self._tag_warning_lines(semantic.warnings)

    def _tag_issue_lines(self, errors: list[PatakhaError], tag: str) -> None:
        seen: set[int] = set()
        for err in errors:
            if err.line <= 0 or err.line in seen:
                continue
            seen.add(err.line)
            self.editor.tag_add(tag, f"{err.line}.0", f"{err.line}.end+1c")

    def _tag_warning_lines(self, warnings: list[PatakhaWarning]) -> None:
        seen: set[int] = set()
        for warning in warnings:
            if warning.line <= 0 or warning.line in seen:
                continue
            seen.add(warning.line)
            self.editor.tag_add("warning_line", f"{warning.line}.0", f"{warning.line}.end+1c")

    def _on_tab_pressed(self, _event: tk.Event) -> str:
        self.editor.insert(tk.INSERT, "    ")
        return "break"

    def _on_return_pressed(self, _event: tk.Event) -> str:
        insert_idx = self.editor.index(tk.INSERT)
        line_start = f"{insert_idx} linestart"
        before = self.editor.get(line_start, insert_idx)
        after = self.editor.get(insert_idx, f"{insert_idx} lineend")
        base_indent = re.match(r"[ \t]*", before).group(0) if before else ""
        should_indent = before.rstrip().endswith("{")
        extra = "    " if should_indent else ""

        self.editor.insert(tk.INSERT, "\n" + base_indent + extra)
        if should_indent and after.lstrip().startswith("}"):
            cursor = self.editor.index(tk.INSERT)
            self.editor.insert(tk.INSERT, "\n" + base_indent)
            self.editor.mark_set(tk.INSERT, cursor)
        self._schedule_highlight()
        self._schedule_diagnostics()
        return "break"

    def _on_key_press(self, event: tk.Event) -> str | None:
        if not event.char:
            return None
        if event.state & 0x4:
            return None
        ch = event.char

        if ch in OPEN_CLOSE_PAIRS:
            close = OPEN_CLOSE_PAIRS[ch]
            if self.editor.tag_ranges("sel"):
                start = self.editor.index("sel.first")
                end = self.editor.index("sel.last")
                selected = self.editor.get(start, end)
                self.editor.delete(start, end)
                self.editor.insert(start, f"{ch}{selected}{close}")
                cursor_offset = len(selected) + 1
                self.editor.mark_set(tk.INSERT, f"{start}+{cursor_offset}c")
            else:
                idx = self.editor.index(tk.INSERT)
                self.editor.insert(idx, ch + close)
                self.editor.mark_set(tk.INSERT, f"{idx}+1c")
            self._schedule_highlight()
            self._schedule_diagnostics()
            return "break"

        if ch in {")", "]", "}", '"', "'"}:
            idx = self.editor.index(tk.INSERT)
            next_char = self.editor.get(idx, f"{idx}+1c")
            if next_char == ch:
                self.editor.mark_set(tk.INSERT, f"{idx}+1c")
                return "break"
        return None

    def _on_backspace(self, _event: tk.Event) -> str | None:
        idx = self.editor.index(tk.INSERT)
        if idx == "1.0":
            return None
        prev_char = self.editor.get(f"{idx}-1c", idx)
        next_char = self.editor.get(idx, f"{idx}+1c")
        if prev_char in OPEN_CLOSE_PAIRS and OPEN_CLOSE_PAIRS[prev_char] == next_char:
            self.editor.delete(f"{idx}-1c", f"{idx}+1c")
            self._schedule_highlight()
            self._schedule_diagnostics()
            return "break"
        return None

    def _tag_regex(self, pattern: str, tag: str, text: str, flags: int = 0) -> None:
        for match in re.finditer(pattern, text, flags):
            self._tag_span(tag, match.start(), match.end())

    def _tag_function_names(self, text: str) -> None:
        pattern = r"\bkaam\s+(?:bhai|decimal|float|bool|text|khali|void|[A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("
        for match in re.finditer(pattern, text):
            if match.lastindex != 1:
                continue
            start = match.start(1)
            end = match.end(1)
            self._tag_span("function", start, end)

    def _tag_span(self, tag: str, start: int, end: int) -> None:
        self.editor.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")


def _executable_path(base_path: Path) -> Path:
    if os.name == "nt":
        return base_path.with_suffix(".exe")
    return Path(str(base_path.with_suffix("")))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="patakha-studio",
        description="Patakha Studio GUI",
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="Optional .bhai file to open at startup",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    initial: Path | None = None
    if args.source:
        initial = Path(args.source)
    app = PatakhaStudio(initial_file=initial)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
