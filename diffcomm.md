# TASK: Build a CLI Tool for Annotated Unified Diffs (`diffcomm`)

## Goal
Build a standalone Python CLI tool named `diffcomm` (`diffcomm.py`) using **Python standard library only (zero dependencies)** that acts as an annotated diff bridge between Jujutsu (`jj`) / Git diffs, human reviewers, and AI agents.

The tool manages `.diffc` files (Diff with Comments), which are standard Unified Diffs enriched with Markdown blockquote comments placed directly below target code lines.

---

## 1. File Format Spec (`.diffc`)

A `.diffc` file is a valid standard Unified Diff with inline comments.

### Format Rules
- Preserves standard Unified Diff elements:
  - File headers (`diff --git a/... b/...`, `--- a/...`, `+++ b/...`)
  - Hunk headers (`@@ -old_start,old_count +new_start,new_count @@`)
  - Context lines (` `), Deletion lines (`-`), Addition lines (`+`)
- Comments are inserted directly below the target diff line.
- Single blockquote prefix (`>`) for top-level comments:
  `> [HUMAN @ YYYY-MM-DD HH:MM]: <comment text>`
  `> [AI @ YYYY-MM-DD HH:MM]: <comment text>`
- Double blockquote prefix (`> >`) for threaded replies:
  `> > [HUMAN @ YYYY-MM-DD HH:MM]: <reply text>`

---

## 2. CLI Interface & Commands

Implemented using Python standard library `argparse`.

### Command 1: `init`
Captures standard unified diff from `stdin` and writes a `.diffc` file.

```bash
jj diff | python3 diffcomm.py init <output.diffc>
# or
git diff | python3 diffcomm.py init <output.diffc>
```

### Command 2: `comment`
Inserts a comment underneath a specific file and line within a diff hunk.

```bash
python3 diffcomm.py comment <path.diffc> \
  --file <target-file-relative-path> \
  --line <new-line-number|+N|-N|diff-line-index> \
  --author <HUMAN|AI> \
  --text "<comment text>"
```

### Command 3: `reply`
Adds a threaded reply under an existing comment block at a specific line.

```bash
python3 diffcomm.py reply <path.diffc> \
  --file <target-file-relative-path> \
  --line <line-number> \
  --author <HUMAN|AI> \
  --text "<reply text>"
```

### Command 4: `list`
Prints a summary table of all inline comments across the `.diffc` file.

```bash
python3 diffcomm.py list <path.diffc> [--file <path>] [--author <HUMAN|AI>]
```

### Command 5: `show`
Displays the formatted diff and comments with ANSI colors in terminal output.

```bash
python3 diffcomm.py show <path.diffc> [--file <path>] [--no-color]
```

### Command 6: `strip`
Strips out all comment blockquote lines (`^>`) and outputs a clean patch to stdout or file.

```bash
python3 diffcomm.py strip <path.diffc> [-o clean.patch]
```

### Command 7: `validate`
Verifies `.diffc` structure, hunk header integrity, and comment block parsing.

```bash
python3 diffcomm.py validate <path.diffc>
```

---

## 3. Internal Architecture & Data Models

### Data Structures (`diffcomm.py`)
- `Comment`: `author`, `timestamp`, `text`, `depth` (1 for top-level, 2+ for replies).
- `DiffLine`: `line_type` (`+`, `-`, ` `), `old_lineno`, `new_lineno`, `content`, `comments: List[Comment]`.
- `Hunk`: `old_start`, `old_count`, `new_start`, `new_count`, `header_text`, `lines: List[DiffLine]`.
- `DiffFile`: `old_path`, `new_path`, `git_headers: List[str]`, `hunks: List[Hunk]`.
- `DiffDocument`: `files: List[DiffFile]`, `header_comments: List[str]`.

---

## 4. Implementation Plan & Architecture

### Architectural Data Flow

```
[stdin / jj diff] ---> init ---> [ .diffc File ]
                                       |
                                  AST Parser
                                       |
                  +--------------------+--------------------+
                  |                    |                    |
             comment/reply            show                 strip
                  |                    |                    |
             AST Mutation          ANSI Color          Clean Patch
                  |                  Viewer              Export
             AST Serializer
                  |
           [ .diffc File ]
```

### Core Algorithms & Design Details

#### 1. Line Addressing Engine
When adding a comment via `--file <path>` and `--line <spec>`:
- **`+N` (New File Line)**: Scans diff lines in `<path>` hunks, tracking `new_lineno`. Matches line where `new_lineno == N`.
- **`-N` (Old File Line)**: Scans diff lines in `<path>` hunks, tracking `old_lineno`. Matches line where `old_lineno == N`.
- **`N` (Raw Line Index)**: 1-based offset relative to the hunk body lines.

#### 2. Comment Attachment & Roundtrip Preservation
- Comments belong to the `DiffLine` immediately preceding them.
- If comments appear before any diff line in a hunk (or at file header), they attach as header comments.
- Serializer formats top-level comments as `> [AUTHOR @ YYYY-MM-DD HH:MM]: text` and nested replies with extra `>` prefixes (`> > [AUTHOR @ ...]: text`).
- `strip` command simply skips any lines matching regex `^\s*>`.

---

## 5. Implementation Phases & Checklist

- [x] **Phase 1: Core AST Data Model & Parser/Serializer**
  - Implement `Comment`, `DiffLine`, `Hunk`, `DiffFile`, `DiffDocument` data classes.
  - Implement `parse_diffc(text: str) -> DiffDocument` supporting unified diff syntax and blockquotes.
  - Implement `serialize_diffc(doc: DiffDocument) -> str` ensuring lossless roundtrip formatting.

- [x] **Phase 2: Core Commands (`init`, `comment`, `strip`)**
  - `init`: Read stdin stream, parse/validate, write to target `.diffc`.
  - Line lookup: Resolve `--file` and `--line` (`+N`, `-N`, index) to exact target `DiffLine`.
  - `comment`: Append new `Comment` object to target `DiffLine` and re-serialize.
  - `strip`: Implement fast-path cleaner returning raw patch without `>` lines.

- [x] **Phase 3: Interactive & Extended Commands (`reply`, `list`, `show`, `validate`)**
  - `reply`: Locate existing comment block at target line and attach sub-comment (`depth = parent_depth + 1`).
  - `list`: Traverse document tree and print formatted table of comments (`File`, `Line`, `Author`, `Timestamp`, `Text`).
  - `show`: Render terminal-formatted diff with ANSI colors (`\033[32m` additions, `\033[31m` deletions, `\033[36m` hunks, `\033[33m` comments).
  - `validate`: Validate hunk offset headers against actual `+`/`-`/` ` line counts and flag malformed comments.

- [x] **Phase 4: Testing & Executable Packaging**
  - Create `test_diffcomm.py` test suite covering:
    - Roundtrip parsing/serialization equivalence.
    - Single-file and multi-file diff comments.
    - Line indexing accuracy across additions and deletions.


