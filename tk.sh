#!/bin/bash

# Configuration
# Resolve the real path of the script to find relative files
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

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
    for s in "backlog" "review" "blocked" "done"; do
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

# Helper: Locate task file by query non-interactively
find_task_file() {
  local query="$1"
  if [[ -z "$query" ]]; then
    return 1
  fi

  # Direct file path
  if [[ -f "$query" ]]; then
    echo "$query"
    return 0
  fi

  # Exact match by filename in $TASKS_DIR
  local exact=$(find "$TASKS_DIR" -not -path '*/.*' -name "$query" 2>/dev/null | head -n 1)
  if [[ -n "$exact" ]]; then
    echo "$exact"
    return 0
  fi

  # Match filename containing query (case insensitive)
  local match=$(find "$TASKS_DIR" -not -path '*/.*' -iname "*$query*.md" 2>/dev/null | head -n 1)
  if [[ -n "$match" ]]; then
    echo "$match"
    return 0
  fi

  return 1
}

# 2. NEW: Create task from template
cmd_new() {
  local project="$1"
  local slug="$2"
  local title="$3"

  # Non-interactive mode (when project and slug are provided)
  if [[ -n "$project" && -n "$slug" ]]; then
    local project_dir="$TASKS_DIR/$project"
    if [[ ! -d "$project_dir" ]]; then
      mkdir -p "$project_dir/backlog" "$project_dir/review" "$project_dir/blocked" "$project_dir/done"
    fi
    local filename="$(date +%Y%m%d)-$slug.md"
    local dest="$project_dir/backlog/$filename"

    cp "$TEMPLATE" "$dest"
    sed -i '' "s/created:.*/created: $(date +%Y-%m-%d)/" "$dest" 2>/dev/null || sed -i "s/created:.*/created: $(date +%Y-%m-%d)/" "$dest"
    if [[ -n "$title" ]]; then
      sed -i '' "s/^# Task:.*/# Task: $title/" "$dest" 2>/dev/null || sed -i "s/^# Task:.*/# Task: $title/" "$dest"
    fi
    echo -e "${GREEN}✅ Task created:${NC} $dest"
    return 0
  fi

  # Interactive fallback using fzf
  local project_sel=$(find "$TASKS_DIR" -maxdepth 1 -type d -not -path "$TASKS_DIR" -not -path "*/.*" -not -path "*00_WORKING*" -not -path "*99_ARCHIVE*" | fzf --prompt "Select Project: ")
  [[ -z "$project_sel" ]] && return

  echo -n "Task title (slug): "
  read slug
  local filename="$(date +%Y%m%d)-$slug.md"
  local dest="$project_sel/backlog/$filename"

  cp "$TEMPLATE" "$dest"
  sed -i '' "s/created:.*/created: $(date +%Y-%m-%d)/" "$dest" 2>/dev/null || sed -i "s/created:.*/created: $(date +%Y-%m-%d)/" "$dest"
  if [ -t 0 ] && command -v nvim &>/dev/null; then
    nvim "$dest"
  else
    echo -e "${GREEN}✅ Task created:${NC} $dest"
  fi
}

# 3. WORK: Link to 00_WORKING
cmd_work() {
  local query="$1"
  local file=""

  if [[ -n "$query" ]]; then
    file=$(find_task_file "$query")
    if [[ -z "$file" ]]; then
      echo -e "${RED}Error: Task matching '$query' not found in $TASKS_DIR${NC}"
      return 1
    fi
  else
    file=$(find "$TASKS_DIR" -not -path '*/.*' -not -path "*/00_WORKING/*" -name "*.md" | fzf --prompt "Activate task: " --height 40% --reverse)
  fi

  if [[ -n "$file" ]]; then
    mkdir -p "$WORKING_DIR"
    ln -sf "$file" "$WORKING_DIR/$(basename "$file")"
    echo -e "${GREEN}🚀 Task linked to 00_WORKING:${NC} $(basename "$file")"
  fi
}

# 4. OPEN: Search and open/print any task
cmd_open() {
  local query="$1"
  local file=""

  if [[ -n "$query" ]]; then
    file=$(find_task_file "$query")
    if [[ -z "$file" ]]; then
      echo -e "${RED}Error: Task matching '$query' not found in $TASKS_DIR${NC}"
      return 1
    fi
  else
    file=$(find "$TASKS_DIR" -not -path '*/.*' -name "*.md" | fzf --preview 'bat --color=always {} 2>/dev/null || cat {}' --height 60% --reverse)
  fi

  if [[ -n "$file" ]]; then
    if [ -t 0 ] && command -v nvim &>/dev/null; then
      nvim "$file"
    else
      echo -e "${BLUE}📄 Task file (${file}):${NC}"
      cat "$file"
    fi
  fi
}

# Helper: Move task to a new status
cmd_move() {
  local target_status="$1"
  local query="$2"
  local file=""

  if [[ -n "$query" ]]; then
    file=$(find_task_file "$query")
    if [[ -z "$file" ]]; then
      echo -e "${RED}Error: Task matching '$query' not found in $TASKS_DIR${NC}"
      return 1
    fi
  else
    file=$(find "$TASKS_DIR" -not -path '*/.*' -not -path "*/00_WORKING/*" -name "*.md" | fzf --prompt "Move to $target_status: " --height 40% --reverse)
  fi

  if [[ -n "$file" ]]; then
    local filename=$(basename "$file")
    local project_dir=$(dirname $(dirname "$file"))
    local dest="$project_dir/$target_status/$filename"

    mkdir -p "$project_dir/$target_status"
    mv "$file" "$dest"

    # Cleanup symlink in 00_WORKING if it exists
    find "$WORKING_DIR" -lname "$file" -delete 2>/dev/null
    find "$WORKING_DIR" -name "$filename" -delete 2>/dev/null

    echo -e "${GREEN}✅ Task moved to $target_status:${NC} $dest"
  fi
}

# 5. REVIEW: Move task to review or initialize a diffc review file
cmd_review_init() {
  local ticket_id="$1"
  local change1="$2"
  local change2="$3"

  if [[ -z "$ticket_id" ]]; then
    echo -e "${RED}Usage: tk review init <ticket-id> [change1] [change2]${NC}"
    return 1
  fi

  # Default change2 to main/master if not provided
  if [[ -z "$change2" ]]; then
    if git rev-parse --verify main >/dev/null 2>&1 || (command -v jj >/dev/null 2>&1 && jj bookmark list 2>/dev/null | grep -q '\bmain\b'); then
      change2="main"
    elif git rev-parse --verify master >/dev/null 2>&1 || (command -v jj >/dev/null 2>&1 && jj bookmark list 2>/dev/null | grep -q '\bmaster\b'); then
      change2="master"
    else
      change2="main"
    fi
  fi

  # Default change1: target branch matching ticket_id, current branch, or ticket_id
  if [[ -z "$change1" ]]; then
    if git rev-parse --verify "$ticket_id" >/dev/null 2>&1 || (command -v jj >/dev/null 2>&1 && jj bookmark list 2>/dev/null | grep -q "\b$ticket_id\b"); then
      change1="$ticket_id"
    else
      local curr_branch=""
      if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        curr_branch=$(git symbolic-ref --short HEAD 2>/dev/null)
      elif command -v jj >/dev/null 2>&1 && jj root >/dev/null 2>&1; then
        curr_branch=$(jj bookmark list 2>/dev/null | grep '\*' | awk '{print $1}')
      fi
      if [[ -n "$curr_branch" && "$curr_branch" != "$change2" ]]; then
        change1="$curr_branch"
      else
        change1="$ticket_id"
      fi
    fi
  fi

  local target_dir="$TASKS_DIR/reviews/$ticket_id"
  mkdir -p "$target_dir"

  local safe_c1=$(echo "$change1" | tr '/' '-')
  local safe_c2=$(echo "$change2" | tr '/' '-')
  local filename="${safe_c1}_${safe_c2}.diffc"
  local dest_path="$target_dir/$filename"

  echo -e "${BLUE}🔍 Generating diff for ticket ${ticket_id} (${change1} vs ${change2})...${NC}"

  local python_bin="python3"
  local diffcomm_script="$SCRIPT_DIR/diffcomm.py"

  if [[ ! -f "$diffcomm_script" ]]; then
    echo -e "${RED}Error: diffcomm.py not found in $SCRIPT_DIR${NC}"
    return 1
  fi

  local diff_output=""
  local diff_status=0

  if command -v jj >/dev/null 2>&1 && jj root >/dev/null 2>&1; then
    diff_output=$(jj diff --from "$change2" --to "$change1" 2>&1)
    diff_status=$?
  elif git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    diff_output=$(git diff "$change2".."$change1" 2>&1)
    diff_status=$?
  else
    echo -e "${RED}Error: Not inside a Jujutsu (jj) or Git repository.${NC}"
    return 1
  fi

  if [[ $diff_status -ne 0 ]]; then
    echo -e "${RED}❌ Diff command failed (${change2} vs ${change1}):${NC}"
    echo "$diff_output"
    return 1
  fi

  echo "$diff_output" | "$python_bin" "$diffcomm_script" init "$dest_path"

  if [[ $? -eq 0 && -f "$dest_path" ]]; then
    echo -e "${GREEN}✅ Generated annotated diffc file:${NC} $dest_path"
  else
    echo -e "${RED}❌ Failed to generate diffc file.${NC}"
    return 1
  fi
}

resolve_diffc_file() {
  local target="$1"

  # Direct file match
  if [[ -n "$target" && -f "$target" ]]; then
    echo "$target"
    return 0
  fi

  # Directory match under ~/tasks/reviews/<target>
  if [[ -n "$target" && -d "$TASKS_DIR/reviews/$target" ]]; then
    local count=$(find "$TASKS_DIR/reviews/$target" -name "*.diffc" 2>/dev/null | wc -l)
    if [[ "$count" -eq 1 ]]; then
      find "$TASKS_DIR/reviews/$target" -name "*.diffc"
      return 0
    elif [[ "$count" -gt 1 ]]; then
      if command -v fzf &>/dev/null; then
        find "$TASKS_DIR/reviews/$target" -name "*.diffc" | fzf --prompt "Select review for $target: " --height 40% --reverse
        return 0
      else
        find "$TASKS_DIR/reviews/$target" -name "*.diffc" | head -n 1
        return 0
      fi
    fi
  fi

  # Interactive search across all review .diffc files
  if command -v fzf &>/dev/null; then
    find "$TASKS_DIR/reviews" -name "*.diffc" 2>/dev/null | fzf --prompt "Select review .diffc file: " --height 40% --reverse
  fi
}

cmd_review() {
  local subcmd="$1"

  case "$subcmd" in
  init)
    shift
    cmd_review_init "$@"
    ;;
  comment | reply | list | show | strip | validate)
    shift
    local target="$1"
    local diffc_file=""

    if [[ -n "$target" && ( "$target" == *.diffc || -d "$TASKS_DIR/reviews/$target" || -f "$target" ) ]]; then
      diffc_file=$(resolve_diffc_file "$target")
      shift
    else
      diffc_file=$(resolve_diffc_file "")
    fi

    if [[ -z "$diffc_file" || ! -f "$diffc_file" ]]; then
      echo -e "${RED}Error: No valid .diffc file specified or selected.${NC}"
      return 1
    fi

    python3 "$SCRIPT_DIR/diffcomm.py" "$subcmd" "$diffc_file" "$@"
    ;;
  diffcomm)
    shift
    python3 "$SCRIPT_DIR/diffcomm.py" "$@"
    ;;
  "")
    cmd_move "review"
    ;;
  *)
    # If subcmd is not a recognized diffcomm subcommand, treat as task movement
    cmd_move "review" "$subcmd"
    ;;
  esac
}

# 6. DONE: Move task to done
cmd_done() {
  cmd_move "done" "$1"
}

# 6b. BLOCKED: Move task to blocked
cmd_blocked() {
  cmd_move "blocked" "$1"
}

# 6c. BACKLOG: Move task to backlog
cmd_backlog() {
  cmd_move "backlog" "$1"
}

# 7. INIT: Initialize structure and symbolic link
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
  mkdir -p "$TASKS_DIR/reviews"
  echo "📂 Folder structure created in $TASKS_DIR"

  # Source paths (SCRIPT_DIR was resolved at script start)
  local source_path="$SCRIPT_DIR/$(basename "$0")"
  local template_source="$SCRIPT_DIR/task_template.md"

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

# 8. PUSH: Push project to remote via rsync
cmd_push() {
  local project_name="$1"
  local remote_input="$2"

  if [[ -z "$project_name" || -z "$remote_input" ]]; then
    echo -e "${RED}Usage: tk push {project_name} {user@host[:path]}${NC}"
    return 1
  fi

  local project_path="$TASKS_DIR/$project_name"

  if [[ ! -d "$project_path" ]]; then
    echo -e "${RED}❌ Project '$project_name' does not exist in $TASKS_DIR${NC}"
    return 1
  fi

  # Normalize remote URL and handle trailing slash
  local remote_url="$remote_input"
  if [[ "$remote_input" != *:* ]]; then
    remote_url="$remote_input:tasks/$project_name"
  fi
  # Ensure remote_url ends with a slash for rsync content sync
  remote_url="${remote_url%/}/"

  echo -e "${BLUE}📤 Pushing '$project_name' -> $remote_url...${NC}"
  rsync -avz --progress "$project_path/" "$remote_url"
}

# 9. PULL: Pull project from remote via rsync
cmd_pull() {
  local project_name="$1"
  local remote_input="$2"

  if [[ -z "$project_name" || -z "$remote_input" ]]; then
    echo -e "${RED}Usage: tk pull {project_name} {user@host[:path]}${NC}"
    return 1
  fi

  local project_path="$TASKS_DIR/$project_name"

  # Create local project directory if it doesn't exist
  if [[ ! -d "$project_path" ]]; then
    echo -e "${YELLOW}📁 Local project folder not found. Creating $project_path...${NC}"
    mkdir -p "$project_path"
  fi

  # Normalize remote URL and handle trailing slash
  local remote_url="$remote_input"
  if [[ "$remote_input" != *:* ]]; then
    remote_url="$remote_input:tasks/$project_name"
  fi
  # Ensure remote_url ends with a slash for rsync content sync
  remote_url="${remote_url%/}/"

  echo -e "${BLUE}📥 Pulling '$project_name' <- $remote_url...${NC}"
  rsync -avz --progress "$remote_url" "$project_path/"
}

# 10. PROJ: Create project structure
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
  mkdir -p "$project_path/review"
  mkdir -p "$project_path/blocked"
  mkdir -p "$project_path/done"

  echo -e "${GREEN}✅ Project created in $project_path${NC}"
}

# --- HELP FUNCTIONS ---

show_help() {
  echo -e "${BLUE}tk - Minimalist Task Manager${NC}"
  echo -e "Usage: tk {command|--flag} [args]\n"
  echo -e "Interactive & Non-Interactive Commands:"
  echo -e "  ${GREEN}init | --init${NC}                            Initialize folder structure and link tk to ~/bin"
  echo -e "  ${GREEN}proj | --proj {name}${NC}                     Create a new project structure"
  echo -e "  ${GREEN}status | ls | --status${NC}                   Show current focus and active projects summary"
  echo -e "  ${GREEN}new | --new {proj} {slug} [title]${NC}        Create task (non-interactive if args provided)"
  echo -e "  ${GREEN}work | --work {task-query}${NC}               Link task to 00_WORKING (non-interactive if arg provided)"
  echo -e "  ${GREEN}review | --review {task-query}${NC}           Move task to 'review' folder"
  echo -e "  ${GREEN}done | --done {task-query}${NC}               Move task to 'done' folder"
  echo -e "  ${GREEN}blocked | --blocked {task-query}${NC}         Move task to 'blocked' folder"
  echo -e "  ${GREEN}backlog | --backlog {task-query}${NC}         Move task to 'backlog' folder"
  echo -e "  ${GREEN}open | --open {task-query}${NC}               Open or view task contents"
  echo -e "\nDiff Review Commands (via diffcomm):"
  echo -e "  ${GREEN}review init <id> [c1] [c2]${NC}               Generate .diffc review file for ticket"
  echo -e "  ${GREEN}review show <id|file>${NC}                    Display colorized diff and inline comments"
  echo -e "  ${GREEN}review comment <id|file> [args]${NC}          Add inline comment to target file & line"
  echo -e "  ${GREEN}review reply <id|file> [args]${NC}            Add threaded reply to an existing comment"
  echo -e "  ${GREEN}review list <id|file>${NC}                    List all inline comments in tabular view"
  echo -e "  ${GREEN}review strip <id|file> [-o file]${NC}         Export clean patch without comments"
  echo -e "  ${GREEN}review validate <id|file>${NC}              Validate hunk header line counts & syntax"
  echo -e "\nRemote Sync Commands:"
  echo -e "  ${GREEN}push | --push {proj} {host}${NC}              Push project folder to remote (~/tasks/)"
  echo -e "  ${GREEN}pull | --pull {proj} {host}${NC}              Pull project folder from remote (~/tasks/)"
  echo -e "\nHelp Options:"
  echo -e "  ${YELLOW}--help | -h${NC}                              Show this help message"
  echo -e "  ${YELLOW}--help-ai-jira-sync${NC}                     Show guide for AI-driven Jira task syncing"
}

show_jira_help() {
  local jira_guide="$SCRIPT_DIR/jira-acli-task-creation.md"

  if [ -f "$jira_guide" ]; then
    if command -v bat &>/dev/null; then
      bat --style=plain --paging=never "$jira_guide"
    else
      cat "$jira_guide"
    fi
  else
    echo -e "${RED}Error: jira-acli-task-creation.md not found in $SCRIPT_DIR${NC}"
  fi
}

# --- MAIN LOGIC ---

case "$1" in
status | list | ls | --status | --ls) cmd_status ;;
new | --new) cmd_new "$2" "$3" "$4" ;;
work | current | cur | --work | --cur | --current) cmd_work "$2" ;;
open | --open) cmd_open "$2" ;;
review | --review) cmd_review "${@:2}" ;;
done | --done) cmd_done "$2" ;;
blocked | --blocked) cmd_blocked "$2" ;;
backlog | --backlog) cmd_backlog "$2" ;;
init | --init) cmd_init ;;
push | --push) cmd_push "$2" "$3" ;;
pull | --pull) cmd_pull "$2" "$3" ;;
project | proj | --proj | --project) cmd_proj "$2" ;;
--help | -h) show_help ;;
--help-ai-jira-sync) show_jira_help ;;
*)
  show_help
  exit 1
  ;;
esac
