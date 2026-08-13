# tk - Minimalist Task Manager

`tk` is a lightweight command-line tool written in Bash for managing tasks and projects using Markdown files. It is designed to be fast, visual, and compatible with terminal-based workflows.

## 🚀 Features

- **Visual Overview:** Quickly see your current focus and the status of your projects.
- **FZF-powered Workflow:** Interactive selection of projects and tasks.
- **Native Markdown:** All tasks are `.md` files, allowing you to use any text editor.
- **Organized Structure:** Automatic classification into `backlog`, `review`, `blocked`, and `done`.

## 🛠 Requirements

For `tk` to function correctly, you need the following installed:

- **Bash** (v4+)
- [**fzf**](https://github.com/junegunn/fzf): For interactive searching.
- [**bat**](https://github.com/sharkdp/bat): For task previews (optional but recommended).
- [**Neovim (nvim)**](https://neovim.io/): As the default editor for tasks.

## 📂 Directory Structure

The script expects your tasks directory to be at `$HOME/tasks` with the following structure:

```text
~/tasks/
├── .templates/
│   └── task.md         # Base template for new tasks
├── 00_WORKING/         # Symbolic links to active tasks
├── Project_A/
│   ├── backlog/
│   ├── review/
│   ├── blocked/
│   └── done/
└── Project_B/
    └── ...
```

## ⌨️ Usage

### `tk init`
Sets up the directory structure in `~/tasks`, creates a default task template, and links the script to `~/bin/tk`.

### `tk proj {project_name}`
Creates the necessary folder structure (`backlog`, `review`, `blocked`, `done`) for a new project within `~/tasks`.

### `tk status`
Shows a summary of what you have in `00_WORKING` (your current focus) and a task count by status for each active project.

### `tk new`
Creates a new task from the template in the `backlog` directory of a selected project. Prompts for a "slug" for the filename.

### `tk work`
Allows you to select a task from any project to create a symbolic link in `00_WORKING`, marking it as your current priority.

### `tk review [subcommand]`
Move a task to the `review/` folder of its project (when run without subcommands), or manage ticket diff reviews using `diffcomm`:

```bash
# Initialize a review .diffc file for a ticket
tk review init PROJ-123 [change1] [change2]

# Display diff with document line numbers on the left margin
tk review show PROJ-123 -n

# Add a comment using physical document line number (e.g., line 8 from `show -n`)
tk review comment PROJ-123 8 --author HUMAN --text "Check validity logic"

# Or add a comment using --file and --line
tk review comment PROJ-123 --file src/app.py --line +12 --author HUMAN --text "Review line 12"

# Reply to an existing comment (e.g. at line 9)
tk review reply PROJ-123 9 --author AI --text "Resolved"

# List all comments in tabular summary format
tk review list PROJ-123

# Export clean patch without blockquote comments
tk review strip PROJ-123 -o clean.patch

# Validate diff syntax and hunk line header counts
tk review validate PROJ-123
```

### `tk new [project] [slug] [title]` or `tk --new`
Creates a new task. If `project` and `slug` are provided, runs non-interactively without `fzf` or `nvim` prompts.

### `tk work [task-query]` or `tk --work`
Links a task to `00_WORKING`. If `task-query` (e.g. ticket ID, slug, or file path) is provided, runs non-interactively without `fzf`.

### `tk review [task-query]` or `tk --review`
Moves a task to `review/`. If `task-query` is provided, runs non-interactively without `fzf`.

### `tk done [task-query]` or `tk --done`
Moves a task to `done/`. If `task-query` is provided, runs non-interactively without `fzf`.

### `tk archive [task-query]` or `tk --archive`
Moves a completed task to `99_ARCHIVE/<project>/`. When run interactively, prioritizes `done/` tasks in `fzf`.

### `tk blocked [task-query]` or `tk --blocked`
Moves a task to `blocked/`. If `task-query` is provided, runs non-interactively without `fzf`.

### `tk open [task-query]` or `tk --open`
Views or opens a task. When run non-interactively (e.g. by an AI agent), prints the task content to stdout.

---

## 🤖 AI Agent Non-Interactive Automation Guide

All commands support direct positional parameters and `--flag` aliases for scripting and AI agents:

```bash
# Create task non-interactively
tk --new MyProject PROJ-123-implement-auth "Implement OAuth Login"

# Focus on task
tk --work PROJ-123

# Read task contents
tk --open PROJ-123

# Move task across statuses
tk --review PROJ-123
tk --done PROJ-123
tk --blocked PROJ-123
```

### `tk push {project} {user@host}`
Pushes the content of a local project to the same path on a remote server (`~/tasks/{project}`). Example: `tk push my-project user@server`

### `tk pull {project} {user@host}`
Pulls the content of a remote project from the same path on a remote server (`~/tasks/{project}`) to your local tasks directory. Example: `tk pull my-project user@server`

## 🔧 Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/your-user/tk.git
   cd tk
   ```
2. Grant execution permissions to the script and initialize it:
   ```bash
   chmod +x tk.sh
   ./tk.sh init
   ```
3. Ensure that `~/bin` is in your `$PATH`. If it isn't, add this to your `.zshrc` or `.bashrc`:
   ```bash
   export PATH="$HOME/bin:$PATH"
   ```
