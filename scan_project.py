#!/usr/bin/env python3
"""
Project structure scanner.
Run from project root: python scan_project.py
Outputs: terminal tree + scan_report.md
"""

import os
import ast
import sys
from pathlib import Path
from datetime import datetime
import urllib.request

# ── Config ────────────────────────────────────────────────────────────────────
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "env", ".env", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "node_modules",
    ".idea", ".vscode", "dist", "build", "*.egg-info",
}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}
INCLUDE_EXTENSIONS = {".py", ".toml", ".cfg", ".ini", ".env", ".yaml", ".yml", ".md", ".txt", ".json"}
MAX_DEPTH = 6

# ── ANSI colors ───────────────────────────────────────────────────────────────
C = {
    "dir":    "\033[1;34m",  # bold blue
    "py":     "\033[0;32m",  # green
    "config": "\033[0;33m",  # yellow
    "md":     "\033[0;36m",  # cyan
    "reset":  "\033[0m",
    "header": "\033[1;35m",  # bold magenta
    "dim":    "\033[2m",
    "warn":   "\033[1;31m",  # bold red
}

def color(text: str, kind: str) -> str:
    return f"{C.get(kind, '')}{text}{C['reset']}"


# ── AST summary ───────────────────────────────────────────────────────────────
def summarize_py(path: Path) -> dict:
    """Extract imports, classes, functions, and docstring from a .py file."""
    result = {"imports": [], "classes": [], "functions": [], "docstring": None, "error": None}
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except SyntaxError as e:
        result["error"] = f"SyntaxError: {e}"
        return result

    result["docstring"] = ast.get_docstring(tree)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = node.names[0].name if isinstance(node, ast.Import) else (node.module or "")
            top = module.split(".")[0]
            if top and top not in result["imports"]:
                result["imports"].append(top)
        elif isinstance(node, ast.ClassDef) and node.col_offset == 0:
            result["classes"].append(node.name)
        elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
            result["functions"].append(node.name)

    return result


# ── Tree builder ──────────────────────────────────────────────────────────────
def get_file_color(name: str) -> str:
    ext = Path(name).suffix
    if ext == ".py":         return "py"
    if ext in {".toml", ".cfg", ".ini", ".env", ".yaml", ".yml"}: return "config"
    if ext in {".md", ".txt"}: return "md"
    return "dim"


def build_tree(
    root: Path,
    prefix: str = "",
    depth: int = 0,
    tree_lines: list = None,
    file_registry: dict = None,
) -> tuple[list[str], dict]:
    if tree_lines is None: tree_lines = []
    if file_registry is None: file_registry = {}
    if depth > MAX_DEPTH:
        return tree_lines, file_registry

    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return tree_lines, file_registry

    entries = [
        e for e in entries
        if e.name not in EXCLUDE_FILES
        and e.name not in EXCLUDE_DIRS
        and not any(e.name.endswith(x.lstrip("*")) for x in EXCLUDE_DIRS if "*" in x)
        and (e.is_dir() or e.suffix in INCLUDE_EXTENSIONS)
    ]

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "

        if entry.is_dir():
            tree_lines.append(f"{prefix}{connector}{color(entry.name + '/', 'dir')}")
            build_tree(entry, prefix + extension, depth + 1, tree_lines, file_registry)
        else:
            kind = get_file_color(entry.name)
            tree_lines.append(f"{prefix}{connector}{color(entry.name, kind)}")
            rel = str(entry.relative_to(root.parent if depth == 0 else entry.parents[depth]))
            file_registry[str(entry)] = {"rel": str(entry.relative_to(Path.cwd())), "ext": entry.suffix}

    return tree_lines, file_registry


# ── Analysis ──────────────────────────────────────────────────────────────────
def analyze_project(root: Path) -> dict:
    py_files = list(root.rglob("*.py"))
    py_files = [
        f for f in py_files
        if not any(part in EXCLUDE_DIRS for part in f.parts)
    ]

    summaries = {}
    all_imports = {}

    for f in py_files:
        rel = str(f.relative_to(root))
        s = summarize_py(f)
        summaries[rel] = s
        for imp in s["imports"]:
            all_imports[imp] = all_imports.get(imp, 0) + 1

    # Detect entry points
    entry_points = [p for p in py_files if p.name in {"main.py", "__main__.py", "app.py", "run.py", "cli.py"}]

    # Detect config files
    config_files = [
        f for f in root.rglob("*")
        if f.suffix in {".toml", ".cfg", ".ini", ".yaml", ".yml"}
        and not any(part in EXCLUDE_DIRS for part in f.parts)
    ]

    # Structural flags
    flags = []
    if not (root / "README.md").exists():
        flags.append("⚠  No README.md found")
    if not any((root / f).exists() for f in ["pyproject.toml", "setup.cfg", "setup.py"]):
        flags.append("⚠  No pyproject.toml / setup.cfg — not a proper Python package")
    if not any(root.rglob("test_*.py")):
        flags.append("⚠  No test files found (test_*.py)")
    if not (root / ".gitignore").exists():
        flags.append("⚠  No .gitignore")
    if not any((root / v).exists() for v in [".venv", "venv", "env"]):
        flags.append("ℹ  No local virtualenv detected (may be system/conda)")

    top_imports = sorted(all_imports.items(), key=lambda x: -x[1])[:15]

    return {
        "summaries": summaries,
        "entry_points": [str(e.relative_to(root)) for e in entry_points],
        "config_files": [str(c.relative_to(root)) for c in config_files],
        "flags": flags,
        "top_imports": top_imports,
        "py_count": len(py_files),
    }


# ── Report builder ────────────────────────────────────────────────────────────
def build_report(root: Path, tree_lines: list[str], analysis: dict) -> str:
    lines = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# Project Scan Report — {root.name}")
    lines.append(f"_Generated: {ts}_\n")

    lines.append("## Folder Structure\n```")
    # strip ANSI for markdown
    import re
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    for l in tree_lines:
        lines.append(ansi_escape.sub("", l))
    lines.append("```\n")

    lines.append(f"## Summary\n- **Python files:** {analysis['py_count']}")
    lines.append(f"- **Entry points:** {', '.join(analysis['entry_points']) or 'none detected'}")
    lines.append(f"- **Config files:** {', '.join(analysis['config_files']) or 'none'}\n")

    if analysis["flags"]:
        lines.append("## Structural Flags")
        for f in analysis["flags"]:
            lines.append(f"- {f}")
        lines.append("")

    lines.append("## Top Imported Modules")
    for mod, count in analysis["top_imports"]:
        lines.append(f"- `{mod}` — {count} file(s)")
    lines.append("")

    lines.append("## Script Summaries")
    for path, s in analysis["summaries"].items():
        lines.append(f"\n### `{path}`")
        if s["error"]:
            lines.append(f"- ❌ {s['error']}")
            continue
        if s["docstring"]:
            lines.append(f"> {s['docstring'].splitlines()[0]}")
        if s["classes"]:
            lines.append(f"- **Classes:** {', '.join(s['classes'])}")
        if s["functions"]:
            lines.append(f"- **Functions:** {', '.join(s['functions'])}")
        if s["imports"]:
            lines.append(f"- **Imports:** {', '.join(s['imports'])}")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    print(f"\n{color('Project Scanner', 'header')} — {color(str(root), 'dir')}\n")

    tree_lines, _ = build_tree(root)
    for line in tree_lines:
        print(line)

    print(f"\n{color('Analyzing Python files...', 'header')}")
    analysis = analyze_project(root)

    print(f"\n{color('Entry points:', 'py')} {', '.join(analysis['entry_points']) or 'none detected'}")
    print(f"{color('Config files:', 'config')} {len(analysis['config_files'])} found")
    print(f"{color('Python files:', 'py')} {analysis['py_count']}")

    if analysis["flags"]:
        print(f"\n{color('Structural flags:', 'warn')}")
        for f in analysis["flags"]:
            print(f"  {f}")

    print(f"\n{color('Top imports:', 'header')}")
    for mod, count in analysis["top_imports"]:
        print(f"  {mod:<25} {color(f'{count} file(s)', 'dim')}")

    report = build_report(root, tree_lines, analysis)
    out = root / "scan_report.md"
    out.write_text(report, encoding="utf-8")
    print(f"\n{color('Report written to:', 'header')} {color(str(out), 'config')}\n")


if __name__ == "__main__":
    main()