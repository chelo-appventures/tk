#!/usr/bin/env python3
"""Board — render ~/tasks as Trello-like boards.

Two modes:

    board.py build  [--out FILE] [--project NAME] [--open]
        Render a single self-contained HTML file with one board per project.

    board.py serve  [--port PORT] [--project NAME] [--no-open]
        Serve the board locally with live drag & drop: dropping a card in
        another column moves the underlying markdown file, exactly like
        `tk review|done|blocked|backlog` does.

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

TASKS_DIR = Path(os.environ.get("TK_TASKS_DIR", Path.home() / "tasks")).expanduser()
DEFAULT_OUT = Path.home() / ".tk" / "board" / "index.html"

STATUS_DIRS = ("backlog", "review", "blocked", "done")

STATUS_META = {
    "backlog": {"label": "Backlog", "icon": "📋"},
    "review": {"label": "Review", "icon": "🔍"},
    "blocked": {"label": "Blocked", "icon": "⛔"},
    "done": {"label": "Done", "icon": "✅"},
}

# Directories under ~/tasks that are not projects.
NON_PROJECT_DIRS = {"00_WORKING", "99_ARCHIVE", "reviews", "review", "done"}

SECTION_KEYWORDS = (
    ("description", ("description", "descripci", "context", "resumen")),
    ("todo", ("todo", "checklist", "acceptance")),
    ("notes", ("notes", "notas")),
    ("plan", ("plan",)),
    ("references", ("reference", "referencia", "refs", "links")),
)

META_RE = re.compile(r"^\s*[-*]\s+\*\*(.+?):\*\*\s*(.*)$")
TODO_RE = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s*(.*)$")
ID_RE = re.compile(r"\[([^\]]+)\]")


# --------------------------------------------------------------------------- #
# Markdown helpers
# --------------------------------------------------------------------------- #

def md_inline(text: str) -> str:
    """Very small inline markdown -> HTML converter (input is already escaped)."""
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text,
    )
    return text


def md_to_html(text: str) -> str:
    """Block-level markdown -> HTML. Used for task detail rendering."""
    if not text:
        return ""

    out: list[str] = []
    list_open = False
    para: list[str] = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    def close_para() -> None:
        if para:
            out.append(f"<p>{md_inline(html.escape(' '.join(para)))}</p>")
            para.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_list()
            close_para()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            close_list()
            close_para()
            level = min(len(heading.group(1)) + 2, 6)
            out.append(f"<h{level}>{md_inline(html.escape(heading.group(2)))}</h{level}>")
            continue

        if re.match(r"^\s*([-*_])\1{2,}\s*$", line):
            close_list()
            close_para()
            out.append("<hr>")
            continue

        quote = re.match(r"^\s*&gt;\s?(.*)$", line) or re.match(r"^\s*>\s?(.*)$", line)
        if quote:
            close_list()
            close_para()
            out.append(f"<blockquote>{md_inline(html.escape(quote.group(1)))}</blockquote>")
            continue

        bullet = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if bullet:
            close_para()
            if not list_open:
                out.append("<ul>")
                list_open = True
            out.append(f"<li>{md_inline(html.escape(bullet.group(1)))}</li>")
            continue

        close_list()
        para.append(line.strip())

    close_list()
    close_para()
    return "\n".join(out)


def classify_section(heading: str) -> str:
    low = heading.lower()
    for key, words in SECTION_KEYWORDS:
        if any(word in low for word in words):
            return key
    return "other"


# --------------------------------------------------------------------------- #
# Task parsing
# --------------------------------------------------------------------------- #

def parse_task(path: Path, project: str) -> dict:
    """Read a task markdown file into a structured dict."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw = ""

    title = path.stem
    meta: dict[str, str] = {}
    sections: dict[str, list[str]] = {"_head": [], "other": []}
    current = "_head"

    for line in raw.splitlines():
        h2 = re.match(r"^##\s+(.*)$", line)
        if h2:
            current = classify_section(h2.group(1))
            sections.setdefault(current, [])
            continue

        if current == "_head":
            if line.startswith("# "):
                title = line[2:].strip()
                continue
            m = META_RE.match(line)
            if m:
                meta[m.group(1).strip().lower()] = m.group(2).strip()
                continue

        sections.setdefault(current, []).append(line)

    # Title: strip the "Task:" prefix and a leading "[ID]" tag.
    title = re.sub(r"^task:\s*", "", title, flags=re.IGNORECASE)
    id_match = ID_RE.match(title)
    task_id = meta.get("id", "").strip()
    if id_match:
        task_id = task_id or id_match.group(1).strip()
        title = title[id_match.end():].strip()
    title = re.sub(r"\s+", " ", title) or path.stem

    created = meta.get("created", "").strip()
    if created.startswith("$("):  # unresolved template placeholder
        created = ""

    status = meta.get("status", "").strip().lstrip("#").strip().lower()

    description = "\n".join(sections.get("description", [])).strip()
    plan = "\n".join(sections.get("plan", [])).strip()
    notes_raw = "\n".join(sections.get("notes", [])).strip()
    references = "\n".join(sections.get("references", [])).strip()

    todos: list[dict] = []
    for line in sections.get("todo", []):
        m = TODO_RE.match(line)
        if m:
            todos.append({"done": m.group(1).lower() == "x", "text": m.group(2).strip()})
    if not todos:  # fall back: any checkbox anywhere in the file
        for line in raw.splitlines():
            m = TODO_RE.match(line)
            if m:
                todos.append({"done": m.group(1).lower() == "x", "text": m.group(2).strip()})

    notes: dict[str, str] = {}
    for line in sections.get("notes", []):
        m = META_RE.match(line)
        if m:
            notes[m.group(1).strip().lower()] = m.group(2).strip()

    done_count = sum(1 for t in todos if t["done"])
    total_count = len(todos)

    return {
        "id": task_id,
        "title": title,
        "status": status,
        "created": created,
        "project": meta.get("project", "").strip() or project,
        "file": path.name,
        "path": str(path),
        "relPath": str(path.relative_to(path.parents[1])) if len(path.parents) > 1 else str(path),
        "description": description,
        "plan": plan,
        "notes": notes,
        "notesRaw": notes_raw,
        "references": references,
        "todos": todos,
        "phase": notes.get("phase", ""),
        "dependsOn": notes.get("depends on", "") or notes.get("depends_on", ""),
        "blocks": notes.get("blocks", ""),
        "spec": notes.get("spec section", "") or notes.get("spec", ""),
        "bookmarks": meta.get("bookmarks", ""),
        "todoDone": done_count,
        "todoTotal": total_count,
        "progress": round(done_count / total_count * 100) if total_count else 0,
    }


# --------------------------------------------------------------------------- #
# Board state
# --------------------------------------------------------------------------- #

def project_label(name: str) -> str:
    return re.sub(r"^\d+[_-]\s*", "", name)


def natural_key(text: str) -> list:
    """Sort key that compares embedded numbers numerically.

    'TRUCTA-ADM-6' -> ['tructa-adm-', 6]
    'TRUCTA-ADM-54' -> ['tructa-adm-', 54]
    So 6 sorts before 54 instead of after it (plain string sort would be wrong).
    """
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text or "")]


def task_sort_key(task: dict) -> tuple:
    """Order cards inside a column: by ticket ID first, then by filename.

    Tasks without an ID (or with a non-numeric one) fall back to their
    filename, which usually starts with the creation date.
    """
    if task["id"]:
        return (0, natural_key(task["id"]), natural_key(task["file"]))
    return (1, natural_key(task["file"]), natural_key(task["file"]))


def discover_projects(tasks_dir: Path) -> list[Path]:
    projects = []
    for entry in sorted(tasks_dir.iterdir()):
        if not entry.is_dir() or entry.is_symlink():
            continue
        if entry.name.startswith("."):
            continue
        if entry.name in NON_PROJECT_DIRS or entry.name.startswith(("00_", "99_")):
            continue
        projects.append(entry)
    return projects


def working_targets(tasks_dir: Path) -> set[str]:
    """Absolute paths of tasks currently linked in 00_WORKING."""
    working_dir = tasks_dir / "00_WORKING"
    targets: set[str] = set()
    if not working_dir.is_dir():
        return targets
    for link in working_dir.iterdir():
        if link.is_symlink():
            try:
                targets.add(os.path.realpath(link))
            except OSError:
                continue
        elif link.is_file():
            targets.add(os.path.realpath(link))
    return targets


def build_state(tasks_dir: Path, project_filter: str | None = None) -> dict:
    tasks_dir = tasks_dir.expanduser()
    if not tasks_dir.is_dir():
        raise SystemExit(f"error: tasks directory not found: {tasks_dir}")

    working = working_targets(tasks_dir)
    projects = []

    for proj_dir in discover_projects(tasks_dir):
        if project_filter and proj_dir.name != project_filter:
            continue

        columns: dict[str, list[dict]] = {s: [] for s in STATUS_DIRS}
        for status in STATUS_DIRS:
            status_dir = proj_dir / status
            if not status_dir.is_dir():
                continue
            for task_file in sorted(status_dir.glob("*.md")):
                task = parse_task(task_file, proj_dir.name)
                task["status"] = status
                task["working"] = os.path.realpath(task_file) in working
                columns[status].append(task)
            columns[status].sort(key=task_sort_key)

        total = sum(len(v) for v in columns.values())
        projects.append(
            {
                "name": proj_dir.name,
                "label": project_label(proj_dir.name),
                "columns": columns,
                "total": total,
                "done": len(columns.get("done", [])),
            }
        )

    projects.sort(key=lambda p: (-p["total"], p["name"]))

    return {
        "projects": projects,
        "generatedAt": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tasksDir": str(tasks_dir),
    }


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #

CSS = """
:root {
  --bg: #0d1117;
  --bg-soft: #131a24;
  --panel: #171f2b;
  --panel-2: #1c2534;
  --line: #263041;
  --text: #e6edf3;
  --muted: #8b98a9;
  --accent: #4c8dff;
  --accent-soft: rgba(76, 141, 255, .15);
  --shadow: 0 8px 24px rgba(0, 0, 0, .38);
  --radius: 14px;
}
html[data-theme="light"] {
  --bg: #eef1f6;
  --bg-soft: #e6eaf2;
  --panel: #ffffff;
  --panel-2: #f6f8fc;
  --line: #dde3ed;
  --text: #17202e;
  --muted: #5c6a7d;
  --accent: #2563eb;
  --accent-soft: rgba(37, 99, 235, .12);
  --shadow: 0 8px 24px rgba(20, 30, 50, .12);
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0;
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(76, 141, 255, .10), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(168, 85, 247, .10), transparent 55%),
    var(--bg);
  color: var(--text);
  font-family: ui-sans-serif, -apple-system, "SF Pro Text", "Segoe UI", Inter, Roboto, sans-serif;
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); }

/* ---------- top bar ---------- */
.topbar {
  position: sticky; top: 0; z-index: 30;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 14px 22px;
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 12px; }
.logo {
  font-size: 22px; width: 42px; height: 42px; display: grid; place-items: center;
  background: linear-gradient(140deg, rgba(76,141,255,.28), rgba(168,85,247,.28));
  border: 1px solid var(--line); border-radius: 12px;
}
.brand h1 { margin: 0; font-size: 17px; letter-spacing: .2px; }
.brand .sub { margin: 2px 0 0; font-size: 12px; color: var(--muted); }
.tools { display: flex; align-items: center; gap: 10px; }
.search {
  display: flex; align-items: center; gap: 8px;
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 10px; padding: 7px 12px; min-width: 260px;
}
.search input {
  border: 0; background: transparent; color: var(--text); outline: none;
  font-size: 13px; width: 100%;
}
.btn {
  border: 1px solid var(--line); background: var(--panel); color: var(--text);
  border-radius: 10px; padding: 8px 12px; cursor: pointer; font-size: 13px;
  transition: background .15s, border-color .15s, transform .05s;
}
.btn:hover { background: var(--panel-2); border-color: var(--accent); }
.btn:active { transform: translateY(1px); }
.btn.icon { padding: 8px 10px; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn.primary:hover { filter: brightness(1.08); }

/* ---------- project tabs ---------- */
.projects {
  display: flex; gap: 8px; flex-wrap: wrap;
  padding: 14px 22px 4px;
}
.tab {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 14px; border-radius: 999px; cursor: pointer;
  border: 1px solid var(--line); background: var(--panel);
  color: var(--muted); font-size: 13px; font-weight: 500;
  transition: all .15s;
}
.tab:hover { color: var(--text); border-color: var(--accent); }
.tab.active { background: var(--accent-soft); border-color: var(--accent); color: var(--text); }
.tab .pill {
  background: var(--bg-soft); border-radius: 999px; padding: 1px 8px;
  font-size: 11px; color: var(--muted);
}
.tab.active .pill { background: rgba(0,0,0,.25); color: var(--text); }

/* ---------- focus strip ---------- */
.focus {
  margin: 10px 22px 0; padding: 10px 14px;
  border: 1px dashed var(--line); border-radius: 12px;
  background: var(--panel); display: flex; gap: 12px; align-items: center;
  flex-wrap: wrap; color: var(--muted); font-size: 13px;
}
.focus .item { display: flex; align-items: center; gap: 8px; color: var(--text); cursor: pointer; }
.focus .item .dot {
  width: 8px; height: 8px; border-radius: 50%; background: #22c55e;
  box-shadow: 0 0 0 4px rgba(34,197,94,.18);
}

/* ---------- board ---------- */
.board { padding: 18px 22px 40px; display: flex; flex-direction: column; gap: 26px; }
.board-group-title {
  font-size: 13px; text-transform: uppercase; letter-spacing: .12em;
  color: var(--muted); margin-bottom: 10px; display: flex; gap: 10px; align-items: center;
}
.columns { display: flex; gap: 16px; align-items: flex-start; overflow-x: auto; padding-bottom: 10px; }
.column {
  flex: 1 1 0; min-width: 280px; max-width: 420px;
  background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 12px;
  display: flex; flex-direction: column; gap: 10px;
  transition: border-color .15s, background .15s;
}
.column.over { border-color: var(--accent); background: var(--accent-soft); }
.col-head { display: flex; align-items: center; gap: 8px; padding: 2px 4px 6px; }
.col-head h2 { margin: 0; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); }
.col-head .count {
  margin-left: auto; background: var(--bg-soft); color: var(--muted);
  border-radius: 999px; padding: 1px 9px; font-size: 12px; font-weight: 600;
}
.cards { display: flex; flex-direction: column; gap: 10px; min-height: 40px; }
.empty { color: var(--muted); font-size: 12px; text-align: center; padding: 18px 6px; border: 1px dashed var(--line); border-radius: 10px; }

/* ---------- card ---------- */
.card {
  background: var(--panel-2); border: 1px solid var(--line);
  border-radius: 12px; padding: 11px 12px; cursor: pointer;
  display: flex; flex-direction: column; gap: 8px;
  transition: transform .12s, border-color .15s, box-shadow .15s;
  position: relative; overflow: hidden;
}
.card:hover { transform: translateY(-2px); border-color: var(--accent); box-shadow: var(--shadow); }
.card.dragging { opacity: .45; }
.card.working { border-color: #22c55e; box-shadow: 0 0 0 1px rgba(34,197,94,.35); }
.card-top { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip {
  font-size: 10.5px; font-weight: 600; letter-spacing: .03em;
  padding: 2px 7px; border-radius: 6px;
  background: var(--bg-soft); color: var(--muted); border: 1px solid transparent;
  white-space: nowrap;
}
.chip.id { background: var(--accent-soft); color: var(--accent); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.chip.phase { border-color: var(--line); }
.chip.pin { background: rgba(34,197,94,.16); color: #4ade80; }
.card-title { margin: 0; font-size: 13.5px; font-weight: 600; line-height: 1.35; }
.card-desc {
  margin: 0; font-size: 12px; color: var(--muted); line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.bar { height: 4px; border-radius: 999px; background: var(--bg-soft); overflow: hidden; }
.bar > span { display: block; height: 100%; background: linear-gradient(90deg, #4c8dff, #a855f7); }
.bar.done > span { background: linear-gradient(90deg, #22c55e, #14b8a6); }
.card-foot { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--muted); }
.card-foot .spacer { margin-left: auto; }
.dot-status { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }

/* ---------- modal ---------- */
.backdrop {
  position: fixed; inset: 0; background: rgba(3, 7, 15, .68);
  backdrop-filter: blur(4px); display: none; z-index: 60;
  align-items: flex-start; justify-content: center; padding: 40px 16px; overflow-y: auto;
}
.backdrop.open { display: flex; }
.modal {
  background: var(--panel); border: 1px solid var(--line); border-radius: 18px;
  width: min(820px, 100%); box-shadow: var(--shadow); overflow: hidden;
}
.modal-head { padding: 18px 22px; border-bottom: 1px solid var(--line); display: flex; gap: 12px; align-items: flex-start; }
.modal-head h2 { margin: 6px 0 0; font-size: 17px; line-height: 1.3; }
.modal-body { padding: 18px 22px 24px; max-height: 68vh; overflow-y: auto; }
.modal-foot {
  padding: 12px 22px; border-top: 1px solid var(--line);
  display: flex; gap: 8px; flex-wrap: wrap; align-items: center; background: var(--panel-2);
}
.modal-foot .spacer { margin-left: auto; }
.meta-grid { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.section-title {
  font-size: 11px; text-transform: uppercase; letter-spacing: .12em;
  color: var(--muted); margin: 20px 0 8px; font-weight: 700;
}
.modal-body ul { margin: 6px 0; padding-left: 20px; }
.modal-body li { margin: 3px 0; line-height: 1.5; }
.modal-body p { line-height: 1.6; margin: 8px 0; }
.modal-body code {
  background: var(--bg-soft); padding: 1px 5px; border-radius: 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px;
}
.modal-body blockquote {
  margin: 8px 0; padding: 6px 14px; border-left: 3px solid var(--accent);
  background: var(--accent-soft); border-radius: 0 8px 8px 0;
}
.todo-list { list-style: none; padding: 0; margin: 6px 0; }
.todo-list li { display: flex; gap: 9px; align-items: flex-start; }
.todo-list .box {
  flex: 0 0 auto; width: 16px; height: 16px; margin-top: 2px; border-radius: 5px;
  border: 1.5px solid var(--line); display: grid; place-items: center; font-size: 11px;
}
.todo-list li.done .box { background: #22c55e; border-color: #22c55e; color: #06280f; }
.todo-list li.done .text { color: var(--muted); text-decoration: line-through; }
.copyline { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11.5px; color: var(--muted); }

/* ---------- stats ---------- */
.stats {
  padding: 12px 22px 26px; color: var(--muted); font-size: 12px;
  display: flex; gap: 18px; flex-wrap: wrap; border-top: 1px solid var(--line);
}
.stats b { color: var(--text); }

.toast {
  position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%) translateY(20px);
  background: var(--panel); border: 1px solid var(--accent); color: var(--text);
  padding: 10px 16px; border-radius: 10px; box-shadow: var(--shadow);
  opacity: 0; pointer-events: none; transition: all .2s; z-index: 80; font-size: 13px;
}
.toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

@media (max-width: 720px) {
  .search { min-width: 140px; }
  .brand .sub { display: none; }
}
"""

JS = r"""
(function () {
  const DATA = window.__TK_BOARD__;
  const LIVE = !!DATA.live;

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const state = {
    project: DATA.projects.length ? DATA.projects[0].name : null,
    query: "",
    theme: localStorage.getItem("tk-board-theme") || "dark",
  };

  // ?theme=light|dark overrides the saved preference (handy for sharing/printing).
  try {
    const forced = new URLSearchParams(location.search).get("theme");
    if (forced === "light" || forced === "dark") state.theme = forced;
  } catch (e) { /* ignore */ }

  // ---------- theme ----------
  function applyTheme() {
    document.documentElement.setAttribute("data-theme", state.theme);
    $("#theme").textContent = state.theme === "dark" ? "🌙" : "☀️";
  }
  $("#theme").addEventListener("click", () => {
    state.theme = state.theme === "dark" ? "light" : "dark";
    localStorage.setItem("tk-board-theme", state.theme);
    applyTheme();
  });
  applyTheme();

  // ---------- helpers ----------
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove("show"), 2200);
  }

  function matches(task) {
    if (!state.query) return true;
    const q = state.query.toLowerCase();
    return (
      (task.title || "").toLowerCase().includes(q) ||
      (task.id || "").toLowerCase().includes(q) ||
      (task.description || "").toLowerCase().includes(q) ||
      (task.phase || "").toLowerCase().includes(q) ||
      (task.file || "").toLowerCase().includes(q)
    );
  }

  function findTask(project, file) {
    const proj = DATA.projects.find((p) => p.name === project);
    if (!proj) return null;
    for (const status of Object.keys(proj.columns)) {
      const hit = proj.columns[status].find((t) => t.file === file);
      if (hit) return hit;
    }
    return null;
  }

  // ---------- rendering ----------
  function renderTabs() {
    const nav = $("#projects");
    const totalAll = DATA.projects.reduce((n, p) => n + p.total, 0);
    const tabs = [{ name: null, label: "All projects", total: totalAll }].concat(DATA.projects);
    nav.innerHTML = tabs
      .map((p) => {
        const active = state.project === p.name ? " active" : "";
        const label = p.label || p.name;
        return `<div class="tab${active}" data-project="${p.name == null ? "" : esc(p.name)}">
          <span>${esc(label)}</span><span class="pill">${p.total}</span></div>`;
      })
      .join("");
    $$(".tab", nav).forEach((tab) => {
      tab.addEventListener("click", () => {
        const name = tab.dataset.project || null;
        state.project = name;
        render();
      });
    });
  }

  function cardHtml(task, project) {
    const chips = [];
    if (task.id) chips.push(`<span class="chip id">${esc(task.id)}</span>`);
    if (task.phase) chips.push(`<span class="chip phase">${esc(task.phase)}</span>`);
    if (task.working) chips.push(`<span class="chip pin">📌 working</span>`);
    const desc = (task.description || "").split("\n").filter(Boolean).join(" ");
    const pct = task.todoTotal ? task.progress : 0;
    const barCls = task.status === "done" ? "bar done" : "bar";
    return `<article class="card${task.working ? " working" : ""}" ${LIVE ? 'draggable="true"' : ""}
        data-project="${esc(project)}" data-file="${esc(task.file)}" data-status="${esc(task.status)}">
      <div class="card-top">${chips.join("")}</div>
      <h3 class="card-title">${esc(task.title)}</h3>
      ${desc ? `<p class="card-desc">${esc(desc)}</p>` : ""}
      ${task.todoTotal ? `<div class="${barCls}"><span style="width:${pct}%"></span></div>` : ""}
      <div class="card-foot">
        ${task.todoTotal ? `<span>✅ ${task.todoDone}/${task.todoTotal}</span>` : "<span>—</span>"}
        <span class="spacer"></span>
        ${task.created ? `<span>${esc(task.created)}</span>` : ""}
      </div>
    </article>`;
  }

  function columnHtml(project, status) {
    const meta = STATUS_META[status];
    const tasks = project.columns[status] || [];
    const visible = tasks.filter(matches);
    const cards = visible.length
      ? visible.map((t) => cardHtml(t, project.name)).join("")
      : `<div class="empty">${tasks.length ? "no matches" : "empty"}</div>`;
    return `<section class="column" data-status="${status}" data-project="${esc(project.name)}">
      <header class="col-head">
        <span>${meta.icon}</span><h2>${esc(meta.label)}</h2>
        <span class="count">${visible.length}${visible.length !== tasks.length ? "/" + tasks.length : ""}</span>
      </header>
      <div class="cards">${cards}</div>
    </section>`;
  }

  function render() {
    renderTabs();

    const projects = state.project
      ? DATA.projects.filter((p) => p.name === state.project)
      : DATA.projects;

    const board = $("#board");
    board.innerHTML = projects
      .map(
        (p) => `<div class="board-group">
          ${state.project ? "" : `<div class="board-group-title">📦 ${esc(p.label)}</div>`}
          <div class="columns">${Object.keys(STATUS_META)
            .map((s) => columnHtml(p, s))
            .join("")}</div>
        </div>`
      )
      .join("");

    // focus strip
    const focus = $("#focus");
    const working = [];
    projects.forEach((p) => {
      Object.values(p.columns).forEach((list) =>
        list.forEach((t) => {
          if (t.working) working.push({ project: p.name, task: t });
        })
      );
    });
    focus.innerHTML = working.length
      ? `<span>🎯 Now working</span>` +
        working
          .map(
            (w) => `<span class="item" data-project="${esc(w.project)}" data-file="${esc(w.task.file)}">
              <span class="dot"></span><b>${esc(w.task.id || w.task.file)}</b> ${esc(w.task.title)}</span>`
          )
          .join("")
      : `<span>🎯 Nothing in <code>00_WORKING</code> — run <code>tk work &lt;task&gt;</code> to pin a task.</span>`;
    $$(".focus .item").forEach((el) =>
      el.addEventListener("click", () => openModal(el.dataset.project, el.dataset.file))
    );

    // stats
    const all = DATA.projects;
    const total = all.reduce((n, p) => n + p.total, 0);
    const done = all.reduce((n, p) => n + p.done, 0);
    $("#stats").innerHTML =
      `<span>📦 <b>${all.length}</b> projects</span>` +
      `<span>🗂️ <b>${total}</b> cards</span>` +
      `<span>✅ <b>${done}</b> done</span>` +
      `<span>🕒 updated <b>${esc(DATA.generatedAt)}</b></span>` +
      `<span>📁 <code>${esc(DATA.tasksDir)}</code></span>` +
      (LIVE ? `<span>🔥 live mode — drag &amp; drop moves the real files</span>`
             : `<span>📄 static snapshot — run <code>tk board serve</code> for live drag &amp; drop</span>`);

    bindCards();
  }

  function bindCards() {
    $$(".card").forEach((card) => {
      card.addEventListener("click", () =>
        openModal(card.dataset.project, card.dataset.file)
      );
      if (!LIVE) return;
      card.addEventListener("dragstart", (ev) => {
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", JSON.stringify({
          project: card.dataset.project,
          file: card.dataset.file,
          from: card.dataset.status,
        }));
        card.classList.add("dragging");
      });
      card.addEventListener("dragend", () => card.classList.remove("dragging"));
    });

    if (!LIVE) return;

    $$(".column").forEach((col) => {
      col.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        col.classList.add("over");
      });
      col.addEventListener("dragleave", () => col.classList.remove("over"));
      col.addEventListener("drop", async (ev) => {
        ev.preventDefault();
        col.classList.remove("over");
        let payload;
        try { payload = JSON.parse(ev.dataTransfer.getData("text/plain")); }
        catch (e) { return; }
        const to = col.dataset.status;
        if (!to || payload.from === to) return;
        const res = await api("/api/move", {
          project: payload.project,
          file: payload.file,
          from: payload.from,
          to: to,
        });
        if (res && res.ok) {
          toast(`Moved to ${STATUS_META[to].label}`);
          location.reload();
        } else {
          toast("Move failed: " + ((res && res.error) || "unknown"));
        }
      });
    });
  }

  // ---------- modal ----------
  async function api(path, body) {
    try {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      return await res.json();
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  }

  function openModal(project, file) {
    const task = findTask(project, file);
    if (!task) return;

    const meta = [];
    if (task.id) meta.push(`<span class="chip id">${esc(task.id)}</span>`);
    meta.push(`<span class="chip">${STATUS_META[task.status].icon} ${esc(STATUS_META[task.status].label)}</span>`);
    if (task.phase) meta.push(`<span class="chip phase">${esc(task.phase)}</span>`);
    if (task.created) meta.push(`<span class="chip">🗓 ${esc(task.created)}</span>`);
    if (task.working) meta.push(`<span class="chip pin">📌 working</span>`);

    const todoHtml = task.todos && task.todos.length
      ? `<ul class="todo-list">${task.todos
          .map(
            (t) => `<li class="${t.done ? "done" : ""}">
              <span class="box">${t.done ? "✓" : ""}</span>
              <span class="text">${esc(t.text)}</span></li>`
          )
          .join("")}</ul>`
      : "<p>No TODO items.</p>";

    const notes = task.notes || {};
    const noteRows = Object.entries(notes)
      .map(([k, v]) => `<li><b>${esc(k)}:</b> ${esc(v)}</li>`)
      .join("");

    const sections = [];
    if (task.description) {
      sections.push(`<div class="section-title">📝 Description</div>${task.descriptionHtml}`);
    }
    if (task.plan) {
      sections.push(`<div class="section-title">📋 Plan</div>${task.planHtml}`);
    }
    sections.push(`<div class="section-title">✅ TODO</div>${todoHtml}`);
    if (noteRows) {
      sections.push(`<div class="section-title">📓 Notes</div><ul>${noteRows}</ul>`);
    }
    if (task.references) {
      sections.push(`<div class="section-title">📎 References</div>${task.referencesHtml}`);
    }

    const moves = Object.keys(STATUS_META)
      .filter((s) => s !== task.status)
      .map(
        (s) =>
          `<button class="btn" data-move="${s}">→ ${STATUS_META[s].icon} ${STATUS_META[s].label}</button>`
      )
      .join("");

    $("#modal-inner").innerHTML = `
      <div class="modal-head">
        <div style="flex:1">
          <div class="meta-grid">${meta.join("")}</div>
          <h2>${esc(task.title)}</h2>
        </div>
        <button class="btn icon" id="modal-close">✕</button>
      </div>
      <div class="modal-body">${sections.join("")}</div>
      <div class="modal-foot">
        ${LIVE ? moves : ""}
        ${LIVE ? `<button class="btn" id="modal-focus">${task.working ? "unfocus" : "📌 focus"}</button>` : ""}
        <span class="spacer"></span>
        <span class="copyline">${esc(task.path)}</span>
        <button class="btn" id="modal-copy">copy path</button>
      </div>`;

    $("#modal").classList.add("open");
    $("#modal-close").addEventListener("click", closeModal);
    $("#modal-copy").addEventListener("click", () => {
      navigator.clipboard.writeText(task.path).then(
        () => toast("Path copied"),
        () => toast("Copy failed")
      );
    });
    if (LIVE) {
      const focusBtn = $("#modal-focus");
      if (focusBtn) {
        focusBtn.addEventListener("click", async () => {
          const res = await api("/api/focus", {
            project: task.project || project,
            file: task.file,
            on: !task.working,
          });
          if (res && res.ok) { toast(res.message || "Updated"); location.reload(); }
        });
      }
      $$("[data-move]", $("#modal-inner")).forEach((btn) =>
        btn.addEventListener("click", async () => {
          const res = await api("/api/move", {
            project: project,
            file: task.file,
            from: task.status,
            to: btn.dataset.move,
          });
          if (res && res.ok) { toast("Moved"); location.reload(); }
          else toast("Move failed");
        })
      );
    }
  }

  function closeModal() { $("#modal").classList.remove("open"); }
  $("#modal").addEventListener("click", (ev) => {
    if (ev.target.id === "modal") closeModal();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeModal();
    if (ev.key === "/" && document.activeElement !== $("#search")) {
      ev.preventDefault();
      $("#search").focus();
    }
  });

  // ---------- search ----------
  $("#search").addEventListener("input", (ev) => {
    state.query = ev.target.value.trim();
    render();
  });

  // ---------- deep links ----------
  // #card=PROJECT/FILE opens that card directly (shareable link).
  // #project=NAME selects a project tab.
  function openFromHash() {
    const m = location.hash.match(/card=([^&]+)/);
    if (m) {
      const raw = decodeURIComponent(m[1]);
      const idx = raw.indexOf("/");
      if (idx > 0) openModal(raw.slice(0, idx), raw.slice(idx + 1));
      return;
    }
    const p = location.hash.match(/project=([^&]+)/);
    if (p) {
      const name = decodeURIComponent(p[1]);
      state.project = name === "all" ? null : name;
      render();
    }
  }
  window.addEventListener("hashchange", openFromHash);

  render();
  openFromHash();
})();
"""

STATUS_META_JSON = json.dumps(STATUS_META)


def render_html(state: dict, live: bool = False) -> str:
    payload = dict(state)
    payload["live"] = live
    # Pre-render markdown blocks so the client needs no markdown engine.
    for project in payload["projects"]:
        for tasks in project["columns"].values():
            for task in tasks:
                task["descriptionHtml"] = md_to_html(task["description"])
                task["planHtml"] = md_to_html(task["plan"])
                task["referencesHtml"] = md_to_html(task["references"])

    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tk board — {html.escape(state.get('tasksDir', ''))}</title>
<style>{CSS}</style>
</head>
<body>
<header class="topbar">
  <div class="brand">
    <span class="logo">🗂️</span>
    <div>
      <h1>tk board</h1>
      <p class="sub" id="subtitle">{html.escape(state.get('tasksDir', ''))}</p>
    </div>
  </div>
  <div class="tools">
    <div class="search">
      <span>🔎</span>
      <input id="search" type="search" placeholder="Search cards…  ( / )" autocomplete="off">
    </div>
    <button class="btn icon" id="theme" title="Toggle theme">🌙</button>
  </div>
</header>

<nav class="projects" id="projects"></nav>
<div class="focus" id="focus"></div>
<main class="board" id="board"></main>
<footer class="stats" id="stats"></footer>

<div class="backdrop" id="modal">
  <div class="modal" id="modal-inner"></div>
</div>

<div class="toast" id="toast"></div>

<script>window.__TK_BOARD__ = {data_json};
window.__TK_STATUS_META__ = {STATUS_META_JSON};</script>
<script>const STATUS_META = window.__TK_STATUS_META__;</script>
<script>{JS}</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Task operations (mirror the tk.sh commands)
# --------------------------------------------------------------------------- #

def locate_task(tasks_dir: Path, project: str, filename: str) -> Path | None:
    proj = tasks_dir / project
    for status in STATUS_DIRS:
        candidate = proj / status / filename
        if candidate.is_file():
            return candidate
    return None


def move_task(tasks_dir: Path, project: str, filename: str, to_status: str) -> Path:
    if to_status not in STATUS_DIRS:
        raise ValueError(f"unknown status: {to_status}")
    src = locate_task(tasks_dir, project, filename)
    if src is None:
        raise FileNotFoundError(f"task not found: {project}/{filename}")

    real_src = os.path.realpath(src)
    dest_dir = tasks_dir / project / to_status
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.move(str(src), str(dest))

    # Same cleanup tk.sh does: drop stale 00_WORKING links.
    working_dir = tasks_dir / "00_WORKING"
    if working_dir.is_dir():
        for link in working_dir.iterdir():
            if not link.is_symlink():
                continue
            try:
                target = os.path.realpath(link)
            except OSError:
                target = ""
            if target == real_src or link.name == filename:
                link.unlink(missing_ok=True)
    return dest


def set_focus(tasks_dir: Path, project: str, filename: str, on: bool = True) -> Path | None:
    task = locate_task(tasks_dir, project, filename)
    if task is None:
        raise FileNotFoundError(f"task not found: {project}/{filename}")

    working_dir = tasks_dir / "00_WORKING"
    working_dir.mkdir(parents=True, exist_ok=True)
    link = working_dir / filename

    if not on:
        if link.is_symlink():
            link.unlink()
        return None

    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(task.resolve())
    return link


# --------------------------------------------------------------------------- #
# Server
# --------------------------------------------------------------------------- #

def make_handler(tasks_dir: Path, project_filter: str | None):
    class BoardHandler(BaseHTTPRequestHandler):
        server_version = "tk-board/1.0"

        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        def _send_json(self, payload: dict, code: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, text: str) -> None:
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send_html(render_html(build_state(tasks_dir, project_filter), live=True))
            elif path == "/api/state":
                self._send_json(build_state(tasks_dir, project_filter))
            else:
                self._send_json({"ok": False, "error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json({"ok": False, "error": "invalid json"}, 400)
                return

            try:
                if path == "/api/move":
                    dest = move_task(
                        tasks_dir,
                        data["project"],
                        data["file"],
                        data["to"],
                    )
                    self._send_json({"ok": True, "path": str(dest)})
                elif path == "/api/focus":
                    res = set_focus(
                        tasks_dir, data["project"], data["file"], bool(data.get("on", True))
                    )
                    self._send_json(
                        {
                            "ok": True,
                            "path": str(res) if res else None,
                            "message": "Pinned to 00_WORKING" if res else "Unpinned",
                        }
                    )
                else:
                    self._send_json({"ok": False, "error": "not found"}, 404)
            except KeyError as exc:
                self._send_json({"ok": False, "error": f"missing field: {exc}"}, 400)
            except (OSError, ValueError, FileNotFoundError) as exc:
                self._send_json({"ok": False, "error": str(exc)}, 400)

    return BoardHandler


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="board.py",
        description="Render ~/tasks as Trello-like boards.",
    )
    parser.add_argument(
        "command", choices=("build", "serve"), nargs="?", default="build"
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output file (build mode)")
    parser.add_argument("--project", default=None, help="only show this project")
    parser.add_argument("--port", type=int, default=8765, help="port for serve mode")
    parser.add_argument("--host", default="127.0.0.1", help="bind address for serve mode")
    parser.add_argument("--tasks-dir", default=str(TASKS_DIR), help="tasks directory")
    parser.add_argument("--open", action="store_true", help="open in the browser")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    parser.add_argument("--quiet", action="store_true", help="suppress messages")
    args = parser.parse_args(argv)

    tasks_dir = Path(args.tasks_dir).expanduser()

    if args.command == "build":
        state = build_state(tasks_dir, args.project)
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_html(state, live=False), encoding="utf-8")
        if not args.quiet:
            projects = len(state["projects"])
            cards = sum(p["total"] for p in state["projects"])
            print(f"✅ Board written to {out}")
            print(f"   {projects} project(s), {cards} card(s)")
            if not args.open:
                print(f"   open it with:  open {out}")
        if args.open and not args.no_open:
            webbrowser.open(out.as_uri())
        return 0

    # serve
    handler = make_handler(tasks_dir, args.project)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    if not args.quiet:
        print(f"🗂️  tk board serving {tasks_dir}", flush=True)
        print(f"   {url}", flush=True)
        print("   Ctrl+C to stop", flush=True)
    if args.open and not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye 👋")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
