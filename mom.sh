#!/usr/bin/env bash

# ==============================================================================
# MOM (MetsuOS Methodology) - Main Root Executable & Language Router
# Version: 0.5.2
# File_Version: 0.5.2.1
# Schema_Version: 0.5.2
# ==============================================================================

set -e

# Directorio raíz del repositorio
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Selección del motor de ejecución (por defecto: py)
ENGINE="${MOM_ENGINE:-py}"

# Procesar banderas de selección de motor si se pasan como primer argumento (--engine=c, --js, etc.)
case "$1" in
    --py|--python)
        ENGINE="py"
        shift
        ;;
    --c)
        ENGINE="c"
        shift
        ;;
    --js|--node)
        ENGINE="js"
        shift
        ;;
esac

case "$ENGINE" in
    py|python)
        TARGET_DIR="$ROOT_DIR/mom-py"
        if [ -f "$TARGET_DIR/mom.sh" ]; then
            exec "$TARGET_DIR/mom.sh" "$@"
        elif [ -f "$TARGET_DIR/cli.py" ]; then
            exec python3 "$TARGET_DIR/cli.py" "$@"
        else
            echo "❌ Error: No se encontró un ejecutable válido en 'mom-py/'." >&2
            exit 1
        fi
        ;;

    c)
        TARGET_DIR="$ROOT_DIR/mom-c"
        if [ -f "$TARGET_DIR/mom.sh" ]; then
            exec "$TARGET_DIR/mom.sh" "$@"
        elif [ -x "$TARGET_DIR/mom" ]; then
            exec "$TARGET_DIR/mom" "$@"
        else
            echo "❌ Error: El motor en C ('mom-c') no está compilado o no existe aún." >&2
            exit 1
        fi
        ;;

    js|node)
        TARGET_DIR="$ROOT_DIR/mom-js"
        if [ -f "$TARGET_DIR/mom.sh" ]; then
            exec "$TARGET_DIR/mom.sh" "$@"
        elif [ -f "$TARGET_DIR/index.js" ]; then
            exec node "$TARGET_DIR/index.js" "$@"
        else
            echo "❌ Error: El motor en JS/Node ('mom-js') no está disponible aún." >&2
            exit 1
        fi
        ;;

    *)
        echo "❌ Error: Motor desconocido '$ENGINE'. Opciones válidas: py, c, js." >&2
        exit 1
        ;;
esac