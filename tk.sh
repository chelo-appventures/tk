#!/bin/bash

# Configuration
TASKS_DIR="$HOME/tasks"
TEMPLATE="$TASKS_DIR/.templates/task.md"
WORKING_DIR="$TASKS_DIR/00_WORKING"

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# --- SUBCOMMANDS ---

# 1. STATUS: View project summary
cmd_status() {
  echo -e "${MAGENTA}🚀 CURRENT FOCUS${NC}"
  find "$WORKING_DIR" -name "*.md" 2>/dev/null | while read -r f; do
    if [ -L "$f" ]; then
      local target=$(readlink "$f")
      local proj=$(basename $(dirname $(dirname "$target")))
      echo -e "  ${GREEN}→${NC} $(basename "$f" .md) ${BLUE}[$proj]${NC}"
    else
      echo -e "  ${GREEN}→${NC} $(basename "$f" .md)"
    fi
  done

  echo -e "\n${BLUE}=== ACTIVE PROJECTS ===${NC}"
  find "$TASKS_DIR" -maxdepth 1 -type d \
    -not -path "$TASKS_DIR" -not -path "*/.*" \
    -not -path "*00_WORKING*" -not -path "*99_ARCHIVE*" | sort | while read -r project; do

    echo -e "${YELLOW}📂 $(basename "$project")${NC}"
    for s in "backlog" "wip" "blocked" "done"; do
      local folder="$project/$s"
      if [ -d "$folder" ]; then
        local count=$(find "$folder" -name "*.md" 2>/dev/null | wc -l)
        if [ "$count" -gt 0 ]; then
          echo -e "  [${s}]: $count"
          find "$folder" -name "*.md" -exec basename {} .md \; | sed 's/^/    - /'
        fi
      fi
    done
    echo ""
  done
}

# 2. NEW: Create task from template
cmd_new() {
  local project=$(find "$TASKS_DIR" -maxdepth 1 -type d -not -path "$TASKS_DIR" -not -path "*/.*" -not -path "*00_WORKING*" -not -path "*99_ARCHIVE*" | fzf --prompt "Select Project: ")
  [[ -z "$project" ]] && return

  echo -n "Task title (slug): "
  read slug
  local filename="$(date +%Y%m%d)-$slug.md"
  local dest="$project/backlog/$filename"

  cp "$TEMPLATE" "$dest"
  sed -i "s/created:.*/created: $(date +%Y-%m-%d)/" "$dest"
  nvim "$dest"
}

# 3. WORK: Link to 00_WORKING
cmd_work() {
  local file=$(find "$TASKS_DIR" -not -path '*/.*' -not -path "*/00_WORKING/*" -name "*.md" | fzf --prompt "Activate task: " --height 40% --reverse)
  if [[ -n "$file" ]]; then
    ln -s "$file" "$WORKING_DIR/$(basename "$file")"
    echo "🚀 Task linked to 00_WORKING"
  fi
}

# 4. OPEN: Search and open any task
cmd_open() {
  local file=$(find "$TASKS_DIR" -not -path 'autoh*/.*' -name "*.md" | fzf --preview 'bat --color=always {}' --height 60% --reverse)
  [[ -n "$file" ]] && nvim "$file"
}

# 5. INIT: Initialize structure and symbolic link
cmd_init() {
  local bin_dir="$HOME/bin"
  local tk_bin="$bin_dir/tk"

  if [[ -f "$tk_bin" && -d "$TASKS_DIR" ]]; then
    echo -e "${YELLOW}⚠️ tk already seems to be initialized.${NC}"
    echo "If you want to reinstall, delete $tk_bin and $TASKS_DIR"
    return 0
  fi

  echo -e "${BLUE}🔧 Initializing tk...${NC}"

  # Basic directories
  mkdir -p "$TASKS_DIR/.templates"
  mkdir -p "$TASKS_DIR/00_WORKING"
  mkdir -p "$TASKS_DIR/99_ARCHIVE"
  echo "📂 Folder structure created in $TASKS_DIR"

  # Determine script and template paths
  local script_dir
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  local source_path="$script_dir/$(basename "$0")"
  local template_source="$script_dir/task_template.md"

  # Copy template from repository if it exists
  if [ -f "$template_source" ]; then
    cp "$template_source" "$TEMPLATE"
    echo "📄 Template copied from $template_source"
  else
    # Fallback: create basic template if file is not found
    cat <<EOF >"$TEMPLATE"
# Task: 

- **Status:** #backlog
- **Created: $(date +%Y-%m-%d)**

## Description
(Quick context)

## TODO
- [ ] 
EOF
    echo "📄 Basic template created (could not find $template_source)"
  fi

  # Create symbolic link in ~/bin/tk
  mkdir -p "$bin_dir"
  ln -sf "$source_path" "$tk_bin"
  echo "🔗 Symbolic link created in $tk_bin"

  echo -e "\n${GREEN}✅ Ready!${NC} Make sure $bin_dir is in your PATH."
}

# 6. SYNC: Synchronize project via rsync
cmd_sync() {
  local project_name="$1"
  local remote_url="$2"

  if [[ -z "$project_name" || -z "$remote_url" ]]; then
    echo -e "${RED}Usage: tk sync {project_name} {user@host:path}${NC}"
    return 1
  fi

  local project_path="$TASKS_DIR/$project_name"

  if [[ ! -d "$project_path" ]]; then
    echo -e "${RED}❌ Project '$project_name' does not exist in $TASKS_DIR${NC}"
    return 1
  fi

  echo -e "${BLUE}🔄 Syncing '$project_name' -> $remote_url...${NC}"
  rsync -avz --progress "$project_path/" "$remote_url/"
}

# 7. PROJ: Create project structure
cmd_proj() {
  local project_name="$1"

  if [[ -z "$project_name" ]]; then
    echo -n "New project name: "
    read project_name
  fi

  local project_path="$TASKS_DIR/$project_name"

  if [[ -d "$project_path" ]]; then
    echo -e "${YELLOW}⚠️ Project '$project_name' already exists.${NC}"
    return 1
  fi

  echo -e "${BLUE}📁 Creating project: $project_name...${NC}"
  mkdir -p "$project_path/backlog"
  mkdir -p "$project_path/blocked"
  mkdir -p "$project_path/done"
  
  echo -e "${GREEN}✅ Project created in $project_path${NC}"
}

# --- HELP FUNCTIONS ---

show_help() {
  echo -e "${BLUE}tk - Minimalist Task Manager${NC}"
  echo -e "Usage: tk {command} [args]\n"
  echo -e "Commands:"
  echo -e "  ${GREEN}init${NC}              Initialize folder structure and link tk to ~/bin"
  echo -e "  ${GREEN}proj {name}${NC}       Create a new project structure (backlog, blocked, done)"
  echo -e "  ${GREEN}status${NC}            Show current focus and active projects summary"
  echo -e "  ${GREEN}new${NC}               Create a new task from template in a project's backlog"
  echo -e "  ${GREEN}work${NC}              Link a task to 00_WORKING (sets current focus)"
  echo -e "  ${GREEN}open${NC}              Search and open any task using fzf and nvim"
  echo -e "  ${GREEN}sync {proj} {url}${NC} Sync project folder to a remote host via rsync"
  echo -e "\nOptions:"
  echo -e "  ${YELLOW}--help${NC}                 Show this help message"
  echo -e "  ${YELLOW}--help-ai-jira-sync${NC}    Show guide for AI-driven Jira task syncing"
}

show_jira_help() {
  local script_dir
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  local jira_guide="$script_dir/jira-acli-task-creation.md"
  
  if [ -f "$jira_guide" ]; then
    if command -v bat &> /dev/null; then
      bat --style=plain --paging=never "$jira_guide"
    else
      cat "$jira_guide"
    fi
  else
    echo -e "${RED}Error: jira-acli-task-creation.md not found in $script_dir${NC}"
  fi
}

# --- MAIN LOGIC ---

case "$1" in
status) cmd_status ;;
new) cmd_new ;;
work) cmd_work ;;
open) cmd_open ;;
init) cmd_init ;;
sync) cmd_sync "$2" "$3" ;;
proj) cmd_proj "$2" ;;
--help) show_help ;;
--help-ai-jira-sync) show_jira_help ;;
*)
  show_help
  exit 1
  ;;
esac
