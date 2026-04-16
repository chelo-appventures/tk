# tk - Minimalist Task Manager

`tk` is a lightweight command-line tool written in Bash for managing tasks and projects using Markdown files. It is designed to be fast, visual, and compatible with terminal-based workflows.

## 🚀 Features

- **Visual Overview:** Quickly see your current focus and the status of your projects.
- **FZF-powered Workflow:** Interactive selection of projects and tasks.
- **Native Markdown:** All tasks are `.md` files, allowing you to use any text editor.
- **Organized Structure:** Automatic classification into `backlog`, `blocked`, and `done`.

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
│   ├── blocked/
│   └── done/
└── Project_B/
    └── ...
```

## ⌨️ Usage

### `tk init`
Sets up the directory structure in `~/tasks`, creates a default task template, and links the script to `~/bin/tk`.

### `tk proj {project_name}`
Creates the necessary folder structure (`backlog`, `blocked`, `done`) for a new project within `~/tasks`.

### `tk status`
Shows a summary of what you have in `00_WORKING` (your current focus) and a task count by status for each active project.

### `tk new`
Creates a new task from the template in the `backlog` directory of a selected project. Prompts for a "slug" for the filename.

### `tk work`
Allows you to select a task from any project to create a symbolic link in `00_WORKING`, marking it as your current priority.

### `tk open`
Global task search with preview (`bat`) and automatic opening in Neovim.

### `tk sync {project} {remote_url}`
Synchronizes the content of a specific project with a remote server using `rsync`. Example: `tk sync my-project user@server:/path/to/dest`

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
