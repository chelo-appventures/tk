# `diffcomm` — Annotated Unified Diff CLI Tool

`diffcomm` is a lightweight, zero-dependency Python CLI tool that acts as a bridge between Jujutsu (`jj diff`) / Git diffs, human reviewers, and AI coding agents. 

It manages **`.diffc` files (Diff with Comments)** — standard Unified Diffs enriched with inline Markdown blockquote comments attached directly beneath target code lines.

---

## 🚀 Features

- **Zero External Dependencies**: Built strictly using the Python standard library (`Python 3.8+`).
- **Standard Patch Compatibility**: Preserves standard unified diff syntax so comments can be stripped cleanly for `git apply` or `jj restore`.
- **Line Addressing Engine**: Supports new line numbers (`+N`), old line numbers (`-N`), and raw hunk line indices.
- **Threaded Discussions**: Nested Markdown blockquotes (`> >`) for replies.
- **Colorized Terminal Output**: Colored viewer for diff additions (`green`), deletions (`red`), hunks (`cyan`), and comments (`yellow`).
- **Integrity Validation**: Hunk header count verification and structural sanity checks.

---

## 🛠 Installation & Requirements

Ensure you have **Python 3.8+** installed.

Clone or download `diffcomm.py` and make it executable:

```bash
chmod +x diffcomm.py
```

Optional: Link to your local binary path:
```bash
ln -s "$(pwd)/diffcomm.py" ~/.local/bin/diffcomm
```

---

## 📖 File Format Spec (`.diffc`)

A `.diffc` file is standard unified diff output enriched with inline blockquote comments:

```diff
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -10,4 +10,5 @@ def calculate_total(items):
     total = 0
     for item in items:
-        total += item.price
+        if item.is_valid():
+            total += item.price
> [HUMAN @ 2026-08-13 14:00]: Should we log invalid items here?
> > [AI @ 2026-08-13 14:02]: Good point! We can add a warning logger or metrics counter.
     return total
```

### Syntax Rules
- **Top-level comment**: `> [AUTHOR @ YYYY-MM-DD HH:MM]: message`
- **Threaded reply**: `> > [AUTHOR @ YYYY-MM-DD HH:MM]: reply message`

---

## ⌨️ Command Usage

### 1. `init` — Create `.diffc` from unified diff
Captures stdin from `jj diff` or `git diff` and saves it to a `.diffc` file.

```bash
# Using Jujutsu:
jj diff | ./diffcomm.py init review.diffc

# Using Git:
git diff | ./diffcomm.py init review.diffc

# From an existing patch file:
./diffcomm.py init review.diffc --input changes.patch
```

---

### 2. `comment` — Add an inline comment
Inserts a top-level blockquote comment directly below a target file line.

```bash
./diffcomm.py comment review.diffc \
  --file src/app.py \
  --line +12 \
  --author HUMAN \
  --text "Check for potential zero division here."
```

#### Line Addressing Syntax:
- `--line +12`: Targets line `12` in the **new file** (`+`).
- `--line -10`: Targets line `10` in the **old file** (`-`).
- `--line 5`: Targets the 5th line within the diff hunk.

---

### 3. `reply` — Add a threaded reply
Adds a nested reply block (`> >`) to an existing comment thread at a specific line.

```bash
./diffcomm.py reply review.diffc \
  --file src/app.py \
  --line +12 \
  --author AI \
  --text "Added zero check guard clause in commit 8f2a1b."
```

---

### 4. `show` — Display formatted diff with ANSI colors
Prints the unified diff and inline comments to the terminal with ANSI color highlighting:
- Additions (`+`) in **Green**
- Deletions (`-`) in **Red**
- Hunk Headers (`@@`) in **Cyan**
- Comments (`>`) in **Yellow / Bold**

```bash
./diffcomm.py show review.diffc

# Plain text output (no colors):
./diffcomm.py show review.diffc --no-color
```

---

### 5. `list` — Summarize all inline comments
Outputs a formatted table of all inline comments across the file.

```bash
./diffcomm.py list review.diffc

# Filter by file path:
./diffcomm.py list review.diffc --file src/app.py

# Filter by author:
./diffcomm.py list review.diffc --author HUMAN
```

**Output Example:**
```text
FILE                      | LINE   | AUTHOR     | TIMESTAMP        | COMMENT
--------------------------------------------------------------------------------
src/app.py                | +12    | HUMAN      | 2026-08-13 14:00 | Check for potential zero division here.
src/app.py                | +12    | AI         | 2026-08-13 14:02 |   Added zero check guard clause in commit 8f2a1b.
```

---

### 6. `strip` — Export clean unified diff patch
Strips all blockquotes (`^>`) and outputs clean unified diff text. This makes the patch compatible with standard tools like `git apply` or `jj restore`.

```bash
# Export clean patch to file:
./diffcomm.py strip review.diffc -o clean.patch

# Apply patch directly:
./diffcomm.py strip review.diffc | git apply
```

---

### 7. `validate` — Check format & line count integrity
Verifies that hunk headers (`@@ -old,count +new,count @@`) accurately match the actual number of addition, deletion, and context lines in the file.

```bash
./diffcomm.py validate review.diffc
```

---

## 🤖 AI Agent & Human Workflow

### Via `tk review` CLI Wrapper
`tk` provides built-in wrappers so you can pass ticket IDs (`PROJ-123`) directly:

1. **Initialize review**: `tk review init PROJ-123` (creates `~/tasks/reviews/PROJ-123/PROJ-123_main.diffc`)
2. **Add comment**: `tk review comment PROJ-123 --file src/main.py --line +45 --author HUMAN --text "Refactor function"`
3. **AI Agent replies**: `tk review reply PROJ-123 --file src/main.py --line +45 --author AI --text "Refactored function"`
4. **Show formatted diff**: `tk review show PROJ-123`
5. **Strip clean patch**: `tk review strip PROJ-123 -o clean.patch`

### Standalone `diffcomm.py` Usage
1. **Developer creates diff**: `jj diff | diffcomm init review.diffc`
2. **Developer adds review notes**: `diffcomm comment review.diffc --file src/main.py --line +45 --author HUMAN --text "Refactor this function"`
3. **AI Agent reads `.diffc`**: Reads comments attached directly next to code lines.
4. **AI Agent replies**: `diffcomm reply review.diffc --file src/main.py --line +45 --author AI --text "Refactored function into modular handler."`
5. **Apply changes**: `diffcomm strip review.diffc | git apply`

---

## 🧪 Testing

Run the built-in test suite:

```bash
python3 -m unittest test_diffcomm.py
```
