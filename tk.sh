#!/bin/bash

# Configuración
TASKS_DIR="$HOME/tasks"
TEMPLATE="$TASKS_DIR/.templates/task.md"
WORKING_DIR="$TASKS_DIR/00_WORKING"

# Colores
BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# --- SUBCOMANDOS ---

# 1. STATUS: Ver resumen de proyectos
cmd_status() {
  echo -e "${MAGENTA}🚀 FOCUS ACTUAL${NC}"
  find "$WORKING_DIR" -name "*.md" 2>/dev/null | while read -r f; do
    if [ -L "$f" ]; then
      local target=$(readlink "$f")
      local proj=$(basename $(dirname $(dirname "$target")))
      echo -e "  ${GREEN}→${NC} $(basename "$f" .md) ${BLUE}[$proj]${NC}"
    else
      echo -e "  ${GREEN}→${NC} $(basename "$f" .md)"
    fi
  done

  echo -e "\n${BLUE}=== PROYECTOS ACTIVOS ===${NC}"
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

# 2. NEW: Crear tarea desde template
cmd_new() {
  local project=$(find "$TASKS_DIR" -maxdepth 1 -type d -not -path "$TASKS_DIR" -not -path "*/.*" -not -path "*00_WORKING*" -not -path "*99_ARCHIVE*" | fzf --prompt "Seleccionar Proyecto: ")
  [[ -z "$project" ]] && return

  echo -n "Título de la tarea (slug): "
  read slug
  local filename="$(date +%Y%m%d)-$slug.md"
  local dest="$project/backlog/$filename"

  cp "$TEMPLATE" "$dest"
  sed -i "s/creado:.*/creado: $(date +%Y-%m-%d)/" "$dest"
  nvim "$dest"
}

# 3. WORK: Vincular a 00_WORKING
cmd_work() {
  local file=$(find "$TASKS_DIR" -not -path '*/.*' -not -path "*/00_WORKING/*" -name "*.md" | fzf --prompt "Activar tarea: " --height 40% --reverse)
  if [[ -n "$file" ]]; then
    ln -s "$file" "$WORKING_DIR/$(basename "$file")"
    echo "🚀 Tarea vinculada a 00_WORKING"
  fi
}

# 4. OPEN: Buscar y abrir cualquier tarea
cmd_open() {
  local file=$(find "$TASKS_DIR" -not -path 'autoh*/.*' -name "*.md" | fzf --preview 'bat --color=always {}' --height 60% --reverse)
  [[ -n "$file" ]] && nvim "$file"
}

# 5. INIT: Inicializar estructura y enlace simbólico
cmd_init() {
  local bin_dir="$HOME/bin"
  local tk_bin="$bin_dir/tk"

  if [[ -f "$tk_bin" && -d "$TASKS_DIR" ]]; then
    echo -e "${YELLOW}⚠️ tk ya parece estar inicializado.${NC}"
    echo "Si deseas reinstalar, elimina $tk_bin y $TASKS_DIR"
    return 0
  fi

  echo -e "${BLUE}🔧 Inicializando tk...${NC}"

  # Directorios básicos
  mkdir -p "$TASKS_DIR/.templates"
  mkdir -p "$TASKS_DIR/00_WORKING"
  mkdir -p "$TASKS_DIR/99_ARCHIVE"
  echo "📂 Estructura de carpetas creada en $TASKS_DIR"

  # Determinar la ruta del script y el template
  local script_dir
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  local source_path="$script_dir/$(basename "$0")"
  local template_source="$script_dir/task_template.md"

  # Copiar plantilla desde el repositorio si existe
  if [ -f "$template_source" ]; then
    cp "$template_source" "$TEMPLATE"
    echo "📄 Plantilla copiada desde $template_source"
  else
    # Fallback: crear plantilla básica si no se encuentra el archivo
    cat <<EOF >"$TEMPLATE"
# Task: 

- **Status:** #backlog
- **Created: $(date +%Y-%m-%d)**

## Description
(Quick context)

## TODO
- [ ] 
EOF
    echo "📄 Plantilla básica creada (no se encontró $template_source)"
  fi

  # Crear enlace simbólico en ~/bin/tk
  mkdir -p "$bin_dir"
  ln -sf "$source_path" "$tk_bin"
  echo "🔗 Enlace simbólico creado en $tk_bin"

  echo -e "\n${GREEN}✅ ¡Listo!${NC} Asegúrate de que $bin_dir esté en tu PATH."
}

# 6. SYNC: Sincronizar proyecto vía rsync
cmd_sync() {
  local project_name="$1"
  local remote_url="$2"

  if [[ -z "$project_name" || -z "$remote_url" ]]; then
    echo -e "${RED}Uso: tk sync {nombre_proyecto} {usuario@host:ruta}${NC}"
    return 1
  fi

  local project_path="$TASKS_DIR/$project_name"

  if [[ ! -d "$project_path" ]]; then
    echo -e "${RED}❌ El proyecto '$project_name' no existe en $TASKS_DIR${NC}"
    return 1
  fi

  echo -e "${BLUE}🔄 Sincronizando '$project_name' -> $remote_url...${NC}"
  rsync -avz --progress "$project_path/" "$remote_url/"
}

# 7. PROJ: Crear estructura de un proyecto
cmd_proj() {
  local project_name="$1"

  if [[ -z "$project_name" ]]; then
    echo -n "Nombre del nuevo proyecto: "
    read project_name
  fi

  local project_path="$TASKS_DIR/$project_name"

  if [[ -d "$project_path" ]]; then
    echo -e "${YELLOW}⚠️ El proyecto '$project_name' ya existe.${NC}"
    return 1
  fi

  echo -e "${BLUE}📁 Creando proyecto: $project_name...${NC}"
  mkdir -p "$project_path/backlog"
  mkdir -p "$project_path/blocked"
  mkdir -p "$project_path/done"
  
  echo -e "${GREEN}✅ Proyecto creado en $project_path${NC}"
}

# --- LÓGICA PRINCIPAL ---

case "$1" in
status) cmd_status ;;
new) cmd_new ;;
work) cmd_work ;;
open) cmd_open ;;
init) cmd_init ;;
sync) cmd_sync "$2" "$3" ;;
proj) cmd_proj "$2" ;;
*)
  echo "Uso: tk {status|new|work|open|init|sync|proj}"
  exit 1
  ;;
esac
