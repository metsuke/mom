#!/usr/bin/env bash

# ==============================================================================
# MOS / MOM CLI Launcher Script (Ubicación: mom-py/mos.sh)
# Lanzador automático de la interfaz de línea de comandos de MOM en Python
# ==============================================================================

# Obtiene la ruta absoluta del directorio donde reside este script (mom-py/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Cambiar al directorio mom-py/ para asegurar el contexto correcto de Poetry y Python
cd "${SCRIPT_DIR}" || exit 1

# Verificar si Poetry está disponible en el sistema
if command -v poetry &> /dev/null; then
    # Ejecuta la CLI a través de Poetry enviándole todos los argumentos pasados al script
    poetry run python cli.py "$@"
else
    # Fallback: intentar ejecutar con python3 directo si Poetry no está en el PATH global
    echo "⚠️ Warning: 'poetry' no está instalado en el PATH. Intentando con 'python3'..."
    python3 cli.py "$@"
fi

# Version: 0.2.6