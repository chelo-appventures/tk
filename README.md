# tk - Gestor de Tareas Minimalista

`tk` es una herramienta ligera de línea de comandos escrita en Bash para gestionar tareas y proyectos utilizando archivos Markdown. Está diseñada para ser rápida, visual y compatible con flujos de trabajo basados en terminal.

## 🚀 Características

- **Resumen visual:** Visualiza rápidamente tu foco actual y el estado de tus proyectos.
- **Flujo basado en FZF:** Selección interactiva de proyectos y tareas.
- **Markdown nativo:** Todas las tareas son archivos `.md`, lo que permite usar cualquier editor de texto.
- **Estructura organizada:** Clasificación automática en `backlog`, `blocked` y `done`.

## 🛠 Requisitos

Para que `tk` funcione correctamente, necesitas tener instalados:

- **Bash** (v4+)
- [**fzf**](https://github.com/junegunn/fzf): Para la búsqueda interactiva.
- [**bat**](https://github.com/sharkdp/bat): Para previsualizar tareas (opcional pero recomendado).
- [**Neovim (nvim)**](https://neovim.io/): Como editor predeterminado para las tareas.

## 📂 Estructura de Directorios

El script espera que tu directorio de tareas esté en `$HOME/tasks` con la siguiente estructura:

```text
~/tasks/
├── .templates/
│   └── task.md         # Plantilla base para nuevas tareas
├── 00_WORKING/         # Enlaces simbólicos a tareas activas
├── Proyecto_A/
│   ├── backlog/
│   ├── blocked/
│   └── done/
└── Proyecto_B/
    └── ...
```

## ⌨️ Uso

### `tk init`
Configura la estructura de directorios en `~/tasks`, crea una plantilla de tarea y vincula el script a `~/bin/tk`.

### `tk proj {nombre_proyecto}`
Crea la estructura de carpetas necesaria (`backlog`, `blocked`, `done`) para un nuevo proyecto dentro de `~/tasks`.

### `tk status`
Muestra el resumen de lo que tienes en `00_WORKING` (tu foco actual) y un conteo de tareas por estado en cada proyecto activo.

### `tk new`
Crea una nueva tarea a partir de la plantilla en el directorio `backlog` de un proyecto seleccionado. Solicita un "slug" para el nombre del archivo.

### `tk work`
Permite seleccionar una tarea de cualquier proyecto para crear un enlace simbólico en `00_WORKING`, marcándola como tu prioridad actual.

### `tk open`
Buscador global de tareas con previsualización (`bat`) y apertura automática en Neovim.

### `tk sync {proyecto} {url_remota}`
Sincroniza el contenido de un proyecto específico con un servidor remoto utilizando `rsync`. Ejemplo: `tk sync mi-proyecto usuario@servidor:/home/ruta`

## 🔧 Instalación

1. Clona este repositorio:
   ```bash
   git clone https://github.com/tu-usuario/tk.git
   cd tk
   ```
2. Dale permisos de ejecución al script e inicialízalo:
   ```bash
   chmod +x tk.sh
   ./tk.sh init
   ```
3. Asegúrate de que `~/bin` esté en tu `$PATH`. Si no lo está, añade esto a tu `.zshrc` o `.bashrc`:
   ```bash
   export PATH="$HOME/bin:$PATH"
   ```
