#!/usr/bin/env python3
"""
diffcomm - Annotated Unified Diff CLI Tool
Preserves standard Unified Diff syntax while adding inline Markdown blockquote comments.
Zero dependencies (Python 3.8+ standard library only).
"""

import argparse
import sys
import os
import re
from datetime import datetime
from typing import List, Optional, Tuple


# --- Data Models ---

class Comment:
    def __init__(self, author: str, timestamp: str, text: str, depth: int = 1):
        self.author = author
        self.timestamp = timestamp
        self.text = text
        self.depth = depth

    def to_diffc(self) -> str:
        prefix = "> " * self.depth
        return f"{prefix}[{self.author} @ {self.timestamp}]: {self.text}"


class DiffLine:
    def __init__(self, prefix: str, content: str, old_lineno: Optional[int] = None, new_lineno: Optional[int] = None):
        self.prefix = prefix          # '+', '-', ' ', '\'
        self.content = content        # text excluding line prefix
        self.old_lineno = old_lineno
        self.new_lineno = new_lineno
        self.comments: List[Comment] = []

    def raw_line(self) -> str:
        if self.prefix == '\\':
            return f"\\ {self.content}"
        return f"{self.prefix}{self.content}"


class Hunk:
    def __init__(self, old_start: int, old_count: int, new_start: int, new_count: int, header_extra: str = ""):
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.header_extra = header_extra
        self.lines: List[DiffLine] = []
        self.header_comments: List[Comment] = []

    def header_line(self) -> str:
        extra = f" {self.header_extra}" if self.header_extra else ""
        return f"@@ -{self.old_start},{self.old_count} +{self.new_start},{self.new_count} @@{extra}"


class DiffFile:
    def __init__(self, old_path: str = "", new_path: str = ""):
        self.old_path = old_path
        self.new_path = new_path
        self.headers: List[str] = []
        self.hunks: List[Hunk] = []
        self.file_comments: List[Comment] = []

    def matches_path(self, target_path: str) -> bool:
        target = target_path.strip()
        def clean(p: str) -> str:
            p = p.strip()
            if p.startswith("a/") or p.startswith("b/"):
                return p[2:]
            return p
        return clean(self.old_path) == clean(target) or clean(self.new_path) == clean(target) or self.old_path == target or self.new_path == target


class DiffDocument:
    def __init__(self):
        self.files: List[DiffFile] = []
        self.preamble: List[str] = []
        self.raw_lines: List[str] = []
        self.doc_line_map: dict = {}


# --- Parser & Serializer ---

RE_HUNK_HEADER = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$")
RE_COMMENT = re.compile(r"^\s*((?:>\s*)+)\[(.*?)\s*@\s*(.*?)]:?\s*(.*)$")
RE_DIFF_GIT = re.compile(r"^diff --git a/(.*) b/(.*)$")
RE_HEADER_OLD = re.compile(r"^--- (?:a/)?(.*)$")
RE_HEADER_NEW = re.compile(r"^\+\+\+ (?:b/)?(.*)$")


def parse_comment_line(line: str) -> Optional[Comment]:
    match = RE_COMMENT.match(line)
    if not match:
        return None
    quotes, author, timestamp, text = match.groups()
    depth = quotes.count(">")
    return Comment(author=author.strip(), timestamp=timestamp.strip(), text=text.strip(), depth=max(1, depth))


def parse_diffc(text: str) -> DiffDocument:
    doc = DiffDocument()
    lines = text.splitlines()
    doc.raw_lines = lines

    current_file: Optional[DiffFile] = None
    current_hunk: Optional[Hunk] = None
    last_diff_line: Optional[DiffLine] = None

    old_line_counter = 0
    new_line_counter = 0

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        doc_lineno = idx + 1

        # Check comment line first
        comment = parse_comment_line(line)
        if comment:
            if last_diff_line is not None:
                last_diff_line.comments.append(comment)
            elif current_hunk is not None:
                current_hunk.header_comments.append(comment)
            elif current_file is not None:
                current_file.file_comments.append(comment)
            doc.doc_line_map[doc_lineno] = (current_file, current_hunk, last_diff_line)
            idx += 1
            continue

        # Check file header start (diff --git)
        if line.startswith("diff --git "):
            current_file = DiffFile()
            doc.files.append(current_file)
            current_hunk = None
            last_diff_line = None
            current_file.headers.append(line)
            m = RE_DIFF_GIT.match(line)
            if m:
                current_file.old_path = m.group(1)
                current_file.new_path = m.group(2)
            doc.doc_line_map[doc_lineno] = (current_file, None, None)
            idx += 1
            continue

        # Check --- line
        if line.startswith("--- "):
            if current_file is None:
                current_file = DiffFile()
                doc.files.append(current_file)
            current_file.headers.append(line)
            m = RE_HEADER_OLD.match(line)
            if m:
                current_file.old_path = m.group(1)
            doc.doc_line_map[doc_lineno] = (current_file, None, None)
            idx += 1
            continue

        # Check +++ line
        if line.startswith("+++ "):
            if current_file is None:
                current_file = DiffFile()
                doc.files.append(current_file)
            current_file.headers.append(line)
            m = RE_HEADER_NEW.match(line)
            if m:
                current_file.new_path = m.group(1)
            doc.doc_line_map[doc_lineno] = (current_file, None, None)
            idx += 1
            continue

        # Check hunk header
        hunk_match = RE_HUNK_HEADER.match(line)
        if hunk_match:
            if current_file is None:
                current_file = DiffFile()
                doc.files.append(current_file)
            
            old_start = int(hunk_match.group(1))
            old_count = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1
            new_start = int(hunk_match.group(3))
            new_count = int(hunk_match.group(4)) if hunk_match.group(4) is not None else 1
            extra = hunk_match.group(5).strip()

            current_hunk = Hunk(old_start, old_count, new_start, new_count, extra)
            current_file.hunks.append(current_hunk)
            last_diff_line = None

            old_line_counter = old_start
            new_line_counter = new_start
            doc.doc_line_map[doc_lineno] = (current_file, current_hunk, None)
            idx += 1
            continue

        # Header metadata lines (e.g., index ..., new file mode ...)
        if current_file is not None and current_hunk is None and not line.startswith(('+', '-', ' ')):
            current_file.headers.append(line)
            doc.doc_line_map[doc_lineno] = (current_file, None, None)
            idx += 1
            continue

        # Preamble before any file header
        if current_file is None:
            doc.preamble.append(line)
            doc.doc_line_map[doc_lineno] = (None, None, None)
            idx += 1
            continue

        # Hunk lines (+, -, ' ', \)
        if current_hunk is not None:
            diff_line = None
            if line.startswith('+'):
                diff_line = DiffLine('+', line[1:], old_lineno=None, new_lineno=new_line_counter)
                new_line_counter += 1
            elif line.startswith('-'):
                diff_line = DiffLine('-', line[1:], old_lineno=old_line_counter, new_lineno=None)
                old_line_counter += 1
            elif line.startswith(' '):
                diff_line = DiffLine(' ', line[1:], old_lineno=old_line_counter, new_lineno=new_line_counter)
                old_line_counter += 1
                new_line_counter += 1
            elif line.startswith('\\'):
                diff_line = DiffLine('\\', line[2:] if line.startswith('\\ ') else line[1:])

            if diff_line:
                current_hunk.lines.append(diff_line)
                last_diff_line = diff_line
                doc.doc_line_map[doc_lineno] = (current_file, current_hunk, diff_line)

        idx += 1

    return doc


def serialize_diffc(doc: DiffDocument) -> str:
    out: List[str] = []

    for line in doc.preamble:
        out.append(line)

    for diff_file in doc.files:
        for header in diff_file.headers:
            out.append(header)
        for comment in diff_file.file_comments:
            out.append(comment.to_diffc())

        for hunk in diff_file.hunks:
            out.append(hunk.header_line())
            for comment in hunk.header_comments:
                out.append(comment.to_diffc())

            for line in hunk.lines:
                out.append(line.raw_line())
                for comment in line.comments:
                    out.append(comment.to_diffc())

    return "\n".join(out) + ("\n" if out else "")


def strip_comments(text: str) -> str:
    lines = text.splitlines()
    clean_lines = [line for line in lines if not RE_COMMENT.match(line) and not line.strip().startswith('>')]
    return "\n".join(clean_lines) + ("\n" if clean_lines else "")


# --- Line Lookup Engine ---

# --- Line Lookup Engine ---

def find_target_by_at_line(doc: DiffDocument, at_line: int) -> Tuple[Optional[DiffFile], Optional[Hunk], Optional[DiffLine]]:
    if at_line in doc.doc_line_map:
        return doc.doc_line_map[at_line]

    if doc.doc_line_map:
        max_line = max(doc.doc_line_map.keys())
        search_start = min(at_line, max_line)
        for l in range(search_start, 0, -1):
            if l in doc.doc_line_map:
                diff_file, hunk, diff_line = doc.doc_line_map[l]
                if diff_line or hunk or diff_file:
                    return diff_file, hunk, diff_line

    return None, None, None


def find_target_line(doc: DiffDocument, target_file: str, line_spec: str) -> Tuple[Optional[DiffFile], Optional[Hunk], Optional[DiffLine]]:
    # Find matching file
    file_obj: Optional[DiffFile] = None
    for f in doc.files:
        if f.matches_path(target_file):
            file_obj = f
            break

    if not file_obj:
        return None, None, None

    spec = line_spec.strip()
    is_new = spec.startswith('+')
    is_old = spec.startswith('-')
    raw_num = int(spec[1:]) if (is_new or is_old) else int(spec)

    # Search strategy:
    # 1. If +N or plain N, search new_lineno == raw_num
    # 2. If -N, search old_lineno == raw_num
    # 3. Fallback: match 1-based index across hunk lines

    for hunk in file_obj.hunks:
        for line in hunk.lines:
            if is_new and line.new_lineno == raw_num:
                return file_obj, hunk, line
            if is_old and line.old_lineno == raw_num:
                return file_obj, hunk, line
            if not is_new and not is_old:
                if line.new_lineno == raw_num or line.old_lineno == raw_num:
                    return file_obj, hunk, line

    # Index fallback
    hunk_line_counter = 0
    for hunk in file_obj.hunks:
        for line in hunk.lines:
            hunk_line_counter += 1
            if hunk_line_counter == raw_num:
                return file_obj, hunk, line

    return file_obj, None, None


def resolve_comment_target(args: argparse.Namespace, doc: DiffDocument) -> Tuple[Optional[DiffFile], Optional[Hunk], Optional[DiffLine], str]:
    # 1. Check --at or positional target_line
    at_val = getattr(args, 'at', None) or getattr(args, 'target_line', None)
    if at_val is not None:
        try:
            at_line = int(at_val)
            diff_file, hunk, diff_line = find_target_by_at_line(doc, at_line)
            return diff_file, hunk, diff_line, f"document line {at_line}"
        except ValueError:
            pass

    # 2. Check --line if given without --file and --line is a plain integer
    if not getattr(args, 'file', None) and getattr(args, 'line', None):
        line_str = str(args.line).strip()
        if not line_str.startswith(('+', '-')):
            try:
                at_line = int(line_str)
                diff_file, hunk, diff_line = find_target_by_at_line(doc, at_line)
                return diff_file, hunk, diff_line, f"document line {at_line}"
            except ValueError:
                pass

    # 3. Traditional --file and --line
    if getattr(args, 'file', None) and getattr(args, 'line', None):
        diff_file, hunk, diff_line = find_target_line(doc, args.file, args.line)
        return diff_file, hunk, diff_line, f"{args.file}:{args.line}"

    return None, None, None, ""


# --- Commands ---

def cmd_init(args: argparse.Namespace) -> int:
    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        if sys.stdin.isatty():
            print("Error: stdin is empty. Pipe a diff into `diffcomm init <file.diffc>` or use `--input`.", file=sys.stderr)
            return 1
        content = sys.stdin.read()

    doc = parse_diffc(content)
    output_text = serialize_diffc(doc)

    output_path = args.output_file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(output_text)

    print(f"Initialized annotated diff file: {output_path}")
    return 0


def cmd_comment(args: argparse.Namespace) -> int:
    path = args.diffc_file
    if not os.path.exists(path):
        print(f"Error: File '{path}' not found.", file=sys.stderr)
        return 1

    with open(path, 'r', encoding='utf-8') as f:
        doc = parse_diffc(f.read())

    diff_file, hunk, diff_line, target_desc = resolve_comment_target(args, doc)

    if not diff_file and not hunk and not diff_line:
        print(f"Error: Target line/file specified not found in '{path}'. Specify document line number (e.g. `diffcomm comment {path} 25 --author HUMAN --text ...`) or `--file` and `--line`.", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    comment = Comment(author=args.author, timestamp=timestamp, text=args.text, depth=1)

    if diff_line:
        diff_line.comments.append(comment)
    elif hunk:
        hunk.header_comments.append(comment)
    elif diff_file:
        diff_file.file_comments.append(comment)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(serialize_diffc(doc))

    print(f"Comment added at {target_desc}")
    return 0


def cmd_reply(args: argparse.Namespace) -> int:
    path = args.diffc_file
    if not os.path.exists(path):
        print(f"Error: File '{path}' not found.", file=sys.stderr)
        return 1

    with open(path, 'r', encoding='utf-8') as f:
        doc = parse_diffc(f.read())

    diff_file, hunk, diff_line, target_desc = resolve_comment_target(args, doc)

    if not diff_file and not hunk and not diff_line:
        print(f"Error: Target line/file specified not found in '{path}'.", file=sys.stderr)
        return 1

    target_comments = diff_line.comments if diff_line else (hunk.header_comments if hunk else diff_file.file_comments if diff_file else [])
    if not target_comments:
        # If no existing comments, initialize top level or append
        parent_depth = 1
    else:
        parent_depth = target_comments[-1].depth

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    reply_comment = Comment(author=args.author, timestamp=timestamp, text=args.text, depth=parent_depth + 1)
    target_comments.append(reply_comment)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(serialize_diffc(doc))

    print(f"Reply added at {target_desc}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    path = args.diffc_file
    if not os.path.exists(path):
        print(f"Error: File '{path}' not found.", file=sys.stderr)
        return 1

    with open(path, 'r', encoding='utf-8') as f:
        doc = parse_diffc(f.read())

    comments_found = []

    for diff_file in doc.files:
        filename = diff_file.new_path or diff_file.old_path
        if getattr(args, 'file', None) and not diff_file.matches_path(args.file):
            continue

        for hunk in diff_file.hunks:
            for line in hunk.lines:
                lineno = f"+{line.new_lineno}" if line.new_lineno else (f"-{line.old_lineno}" if line.old_lineno else "?")
                for c in line.comments:
                    if getattr(args, 'author', None) and c.author.lower() != args.author.lower():
                        continue
                    comments_found.append((filename, lineno, c.author, c.timestamp, c.depth, c.text))

    if not comments_found:
        print("No inline comments found matching criteria.")
        return 0

    print(f"{'FILE':<25} | {'LINE':<6} | {'AUTHOR':<10} | {'TIMESTAMP':<16} | {'COMMENT'}")
    print("-" * 80)
    for filename, lineno, author, ts, depth, text in comments_found:
        indent = "  " * (depth - 1)
        print(f"{filename:<25} | {lineno:<6} | {author:<10} | {ts:<16} | {indent}{text}")

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    path = args.diffc_file
    if not os.path.exists(path):
        print(f"Error: File '{path}' not found.", file=sys.stderr)
        return 1

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    use_color = not args.no_color and sys.stdout.isatty()
    show_lineno = getattr(args, 'line_numbers', False)

    COLOR_RESET = "\033[0m"
    COLOR_GREEN = "\033[32m"
    COLOR_RED = "\033[31m"
    COLOR_CYAN = "\033[36m"
    COLOR_YELLOW = "\033[33m"
    COLOR_GRAY = "\033[90m"
    COLOR_BOLD = "\033[1m"

    lines = content.splitlines()
    max_digits = len(str(len(lines)))

    for idx, line in enumerate(lines, 1):
        prefix_str = f"{idx:>{max_digits}} | " if show_lineno else ""
        if use_color and show_lineno:
            prefix_str = f"{COLOR_GRAY}{prefix_str}{COLOR_RESET}"

        if RE_COMMENT.match(line) or line.strip().startswith('>'):
            if use_color:
                print(f"{prefix_str}{COLOR_YELLOW}{COLOR_BOLD}{line}{COLOR_RESET}")
            else:
                print(f"{prefix_str}{line}")
        elif line.startswith('@@'):
            if use_color:
                print(f"{prefix_str}{COLOR_CYAN}{line}{COLOR_RESET}")
            else:
                print(f"{prefix_str}{line}")
        elif line.startswith('+'):
            if use_color:
                print(f"{prefix_str}{COLOR_GREEN}{line}{COLOR_RESET}")
            else:
                print(f"{prefix_str}{line}")
        elif line.startswith('-'):
            if use_color:
                print(f"{prefix_str}{COLOR_RED}{line}{COLOR_RESET}")
            else:
                print(f"{prefix_str}{line}")
        else:
            print(f"{prefix_str}{line}")

    return 0


def cmd_strip(args: argparse.Namespace) -> int:
    path = args.diffc_file
    if not os.path.exists(path):
        print(f"Error: File '{path}' not found.", file=sys.stderr)
        return 1

    with open(path, 'r', encoding='utf-8') as f:
        clean_patch = strip_comments(f.read())

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(clean_patch)
        print(f"Exported clean patch to: {args.output}")
    else:
        sys.stdout.write(clean_patch)

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = args.diffc_file
    if not os.path.exists(path):
        print(f"Error: File '{path}' not found.", file=sys.stderr)
        return 1

    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    doc = parse_diffc(text)
    errors = []

    for diff_file in doc.files:
        filename = diff_file.new_path or diff_file.old_path
        for hunk in diff_file.hunks:
            actual_old = sum(1 for line in hunk.lines if line.prefix in ('-', ' '))
            actual_new = sum(1 for line in hunk.lines if line.prefix in ('+', ' '))

            if actual_old != hunk.old_count:
                errors.append(f"{filename} {hunk.header_line()}: Old line count mismatch (header: {hunk.old_count}, actual: {actual_old})")
            if actual_new != hunk.new_count:
                errors.append(f"{filename} {hunk.header_line()}: New line count mismatch (header: {hunk.new_count}, actual: {actual_new})")

    if errors:
        print(f"Validation FAILED for '{path}':", file=sys.stderr)
        for err in errors:
            print(f" - {err}", file=sys.stderr)
        return 1

    print(f"Validation PASSED for '{path}'. {len(doc.files)} files, format is valid.")
    return 0


# --- CLI Parser Setup ---

def build_parser() -> argparse.ArgumentParser:
    description = """
diffcomm - Annotated Unified Diff CLI Tool

Bridge Jujutsu (`jj diff`) / Git diffs, human comments, and AI agents.
Manages `.diffc` files (Unified Diffs with inline Markdown blockquote comments).
    """

    epilog = """
Examples:
  jj diff | diffcomm init review.diffc
  diffcomm comment review.diffc --file src/app.py --line +12 --author HUMAN --text "Needs null check"
  diffcomm reply review.diffc --file src/app.py --line +12 --author AI --text "Fixed in commit 8f2a"
  diffcomm show review.diffc
  diffcomm list review.diffc
  diffcomm strip review.diffc -o clean.patch
  diffcomm validate review.diffc

Run 'diffcomm <command> --help' for details on a specific subcommand.
    """

    parser = argparse.ArgumentParser(
        prog="diffcomm",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommand to execute")

    # init
    p_init = subparsers.add_parser(
        "init",
        help="Create a .diffc file from stdin or a patch file",
        description="Reads unified diff from stdin (or --input file) and initializes a .diffc annotated diff file.",
        epilog="Example:\n  jj diff | diffcomm init review.diffc\n  git diff | diffcomm init review.diffc --input changes.patch",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p_init.add_argument("output_file", help="Path to destination .diffc file")
    p_init.add_argument("--input", help="Path to input patch/diff file (if stdin is not used)")
    p_init.set_defaults(func=cmd_init)

    # comment
    p_comment = subparsers.add_parser(
        "comment",
        help="Add an inline blockquote comment to a target line",
        description="Inserts a top-level blockquote comment (> [AUTHOR @ TIMESTAMP]: text) directly beneath the specified line.",
        epilog="Examples:\n  diffcomm comment review.diffc 25 --author HUMAN --text 'Review this line'  (Document line 25)\n  diffcomm comment review.diffc --file src/main.py --line +42 --author HUMAN --text 'Check logic'\n\nLine specs:\n  25  : 25th line in document (visible via `diffcomm show -n`)\n  +42 : Line 42 in NEW file\n  -30 : Line 30 in OLD file",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p_comment.add_argument("diffc_file", help="Path to target .diffc file")
    p_comment.add_argument("target_line", nargs="?", help="Document line number (e.g., 25)")
    p_comment.add_argument("--at", help="Document line number (e.g., --at 25)")
    p_comment.add_argument("--file", help="Target file relative path (e.g., src/main.py)")
    p_comment.add_argument("--line", help="Target line specifier (+N, -N, or document line number)")
    p_comment.add_argument("--author", required=True, help="Author identifier (e.g. HUMAN or AI)")
    p_comment.add_argument("--text", required=True, help="Comment body text")
    p_comment.set_defaults(func=cmd_comment)

    # reply
    p_reply = subparsers.add_parser(
        "reply",
        help="Add a threaded reply to an existing comment block",
        description="Appends a nested reply block (> > [AUTHOR @ TIMESTAMP]: text) under an existing comment thread.",
        epilog="Examples:\n  diffcomm reply review.diffc 25 --author AI --text 'Addressed'\n  diffcomm reply review.diffc --file src/main.py --line +42 --author AI --text 'Addressed'",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p_reply.add_argument("diffc_file", help="Path to target .diffc file")
    p_reply.add_argument("target_line", nargs="?", help="Document line number (e.g., 25)")
    p_reply.add_argument("--at", help="Document line number (e.g., --at 25)")
    p_reply.add_argument("--file", help="Target file relative path")
    p_reply.add_argument("--line", help="Target line specifier (+N, -N, or document line number)")
    p_reply.add_argument("--author", required=True, help="Author identifier (e.g. HUMAN or AI)")
    p_reply.add_argument("--text", required=True, help="Reply body text")
    p_reply.set_defaults(func=cmd_reply)

    # list
    p_list = subparsers.add_parser(
        "list",
        help="Summarize all inline comments in tabular format",
        description="Scans the .diffc file and outputs a formatted overview table of inline comments.",
        epilog="Example:\n  diffcomm list review.diffc\n  diffcomm list review.diffc --author HUMAN\n  diffcomm list review.diffc --file src/main.py",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p_list.add_argument("diffc_file", help="Path to target .diffc file")
    p_list.add_argument("--file", help="Filter summary by relative file path")
    p_list.add_argument("--author", help="Filter summary by comment author")
    p_list.set_defaults(func=cmd_list)

    # show
    p_show = subparsers.add_parser(
        "show",
        help="Display diff and inline comments with ANSI color highlighting",
        description="Renders the annotated diff in terminal with color highlighting (+ green, - red, @@ cyan, > yellow).",
        epilog="Example:\n  diffcomm show review.diffc -n\n  diffcomm show review.diffc --no-color",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p_show.add_argument("diffc_file", help="Path to target .diffc file")
    p_show.add_argument("-n", "--line-numbers", action="store_true", help="Display document line numbers on the left margin")
    p_show.add_argument("--no-color", action="store_true", help="Disable ANSI color codes")
    p_show.set_defaults(func=cmd_show)

    # strip
    p_strip = subparsers.add_parser(
        "strip",
        help="Export a clean patch without blockquote comments",
        description="Strips all blockquote comment lines (> ...) to generate a clean patch compatible with git apply / jj restore.",
        epilog="Example:\n  diffcomm strip review.diffc -o clean.patch\n  diffcomm strip review.diffc | git apply",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p_strip.add_argument("diffc_file", help="Path to target .diffc file")
    p_strip.add_argument("-o", "--output", help="Output file path (default: stdout)")
    p_strip.set_defaults(func=cmd_strip)

    # validate
    p_val = subparsers.add_parser(
        "validate",
        help="Verify diff structure, comment syntax, and hunk line counts",
        description="Checks the .diffc file for structural validity and ensures hunk header counts match actual diff lines.",
        epilog="Example:\n  diffcomm validate review.diffc",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p_val.add_argument("diffc_file", help="Path to target .diffc file")
    p_val.set_defaults(func=cmd_validate)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
