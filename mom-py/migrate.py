#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from typing import Tuple, List

# Garantiza la importación de módulos hermanos
MIGRATE_DIR = Path(__file__).parent.resolve()
if str(MIGRATE_DIR) not in sys.path:
    sys.path.insert(0, str(MIGRATE_DIR))

from schemas import MOMItem, CURRENT_SCHEMA_VERSION
from projects import MOMProjectConfig

def find_projects_dir(start_dir: Path) -> Path:
    """Busca la carpeta data/projects hacia arriba o abajo en la jerarquía de directorios."""
    candidate = start_dir.parent / "data" / "projects"
    if candidate.exists():
        return candidate

    candidate_local = start_dir / "data" / "projects"
    if candidate_local.exists():
        return candidate_local

    curr = start_dir
    while curr != curr.parent:
        p = curr / "data" / "projects"
        if p.exists():
            return p
        curr = curr.parent

    return candidate

def run_repository_migration(projects_root: Path) -> Tuple[int, int, List[str]]:
    """
    Escanea recursivamente TODOS los JSON dentro de data/projects/,
    migra tanto los project.json como las especificaciones atómicas al esquema v0.5.2
    y aplica los valores por defecto (is_private=True, mandatory=True) si faltaban.
    """
    total_processed = 0
    total_migrated = 0
    errors: List[str] = []

    if not projects_root.exists():
        return 0, 0, [f"La ruta de proyectos no existe: {projects_root}"]

    all_json_files = sorted(list(projects_root.rglob("*.json")))

    for json_file in all_json_files:
        # Ignorar archivos compilados en doc/ y vault/
        if "doc/" in str(json_file) or "vault/" in str(json_file):
            continue

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            if not isinstance(raw_data, dict):
                continue

            total_processed += 1
            current_ver = raw_data.get("schema_version")

            # CASO A: Archivo de configuración de proyecto (project.json)
            if json_file.name == "project.json":
                p_config = MOMProjectConfig.from_dict(raw_data)
                
                # Verificar si requería migración (por falta de schema_version, is_private o mandatory)
                needs_update = (
                    current_ver != CURRENT_SCHEMA_VERSION or
                    "is_private" not in raw_data or
                    "mandatory" not in raw_data
                )

                if needs_update:
                    p_config.schema_version = CURRENT_SCHEMA_VERSION
                    with open(json_file, "w", encoding="utf-8") as f:
                        json.dump(p_config.to_dict(), f, indent=2, ensure_ascii=False)
                    total_migrated += 1
                    print(f"  🏢 [Project Config Migrado ➔ Privado/Obligatorio] {json_file.parent.name}/project.json")
                else:
                    print(f"  ✔ [Project Config v{CURRENT_SCHEMA_VERSION}] Ya al día: {json_file.parent.name}/project.json")

            # CASO B: Especificación atómica (MOMItem)
            elif "id" in raw_data:
                item = MOMItem.from_dict(raw_data)

                if current_ver != CURRENT_SCHEMA_VERSION:
                    with open(json_file, "w", encoding="utf-8") as f:
                        json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)
                    total_migrated += 1
                    print(f"  ✅ [Item Migrado ➔ v{CURRENT_SCHEMA_VERSION}] Actualizado: {json_file.name}")
                else:
                    print(f"  ✔ [Item v{CURRENT_SCHEMA_VERSION}] Ya al día: {json_file.name}")

        except Exception as e:
            err_msg = f"Error en '{json_file.relative_to(projects_root)}': {e}"
            errors.append(err_msg)
            print(f"  ❌ {err_msg}")

    return total_processed, total_migrated, errors

def main():
    projects_dir = find_projects_dir(MIGRATE_DIR)
    print("=" * 65)
    print(f" 🔄 MOM Schema & Project Config Migration Utility (v{CURRENT_SCHEMA_VERSION})")
    print("=" * 65)
    print(f"📁 Directorio de proyectos detectado: {projects_dir.resolve()}\n")

    processed, migrated, errors = run_repository_migration(projects_dir)

    print("\n" + "-" * 65)
    print("📊 RESUMEN DE LA MIGRACIÓN:")
    print(f"  • Archivos JSON analizados: {processed}")
    print(f"  • Archivos actualizados a v{CURRENT_SCHEMA_VERSION}: {migrated}")
    print(f"  • Errores detectados: {len(errors)}")
    print("-" * 65)

    if errors:
        print("\n⚠️ Detalle de errores:")
        for err in errors:
            print(f"   • {err}")
        sys.exit(1)
    else:
        print("✨ ¡Proceso completado con éxito!")

if __name__ == "__main__":
    main()

# Version: 0.5.2