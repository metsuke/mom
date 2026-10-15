import sys
import json
import curses
import argparse
import datetime
from pathlib import Path
from typing import Optional, List, Dict

# Garantiza que Python encuentre los módulos locales dentro de 'mom-py'
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Importaciones locales directas
from projects import ProjectManager, MOMInheritedRepository
from compiler import MOMCompiler
from crud import MOMRepository
from schemas import MOMItem, ESAPhase, PriorityEnum, StatusEnum, VerificationMethod, ItemAttributes, ItemMetadata

def ask_confirmation(prompt: str, default: bool = False) -> bool:
    """Solicita confirmación explícita al usuario humano [s/N]."""
    suffix = " [S/n]: " if default else " [s/N]: "
    while True:
        choice = input(f"❓ {prompt}{suffix}").strip().lower()
        if not choice:
            return default
        if choice in ['s', 'si', 'sí', 'y', 'yes']:
            return True
        if choice in ['n', 'no']:
            return False
        print("⚠️ Respuesta no válida. Escribe 's' o 'n'.")

def _curses_multi_select(stdscr, title_header: str, options: List[str], preselected: List[str]) -> List[str]:
    """Renderiza un menú TUI interactivo usando curses para marcar con espacio y confirmar con Enter."""
    curses.curs_set(0)
    stdscr.keypad(True)
    selected = [opt.split(" | ")[0] in preselected for opt in options]
    current_idx = 0

    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, f"=== {title_header} ===", curses.A_BOLD)
        stdscr.addstr(1, 0, "Usa [Flecha Arriba/Abajo] para moverte, [Espacio] para marcar/desmarcar, [Enter] para guardar.")
        stdscr.addstr(2, 0, "--------------------------------------------------------------------------------")

        for idx, option in enumerate(options):
            y = idx + 4
            prefix = "[X] " if selected[idx] else "[ ] "
            if idx == current_idx:
                stdscr.addstr(y, 2, f"> {prefix}{option}", curses.A_REVERSE)
            else:
                stdscr.addstr(y, 2, f"  {prefix}{option}")

        stdscr.refresh()
        key = stdscr.getch()

        if key in [curses.KEY_UP, ord('k')]:
            current_idx = (current_idx - 1) % len(options)
        elif key in [curses.KEY_DOWN, ord('j')]:
            current_idx = (current_idx + 1) % len(options)
        elif key == ord(' '):
            selected[current_idx] = not selected[current_idx]
        elif key in [10, 13, curses.KEY_ENTER]:
            break

    return [options[i].split(" | ")[0] for i, is_sel in enumerate(selected) if is_sel]

def select_parent_projects_interactively(pm: ProjectManager, exclude_project: Optional[str] = None, preselected: Optional[List[str]] = None) -> List[str]:
    available = [
        p.name for p in pm.data_dir.iterdir() 
        if p.is_dir() and (p / "project.json").exists() and p.name != exclude_project
    ]
    if not available:
        print("ℹ️ No hay otros proyectos disponibles de los que heredar.")
        return []

    try:
        return curses.wrapper(_curses_multi_select, "SELECCIÓN DE HERENCIA DE PROYECTOS", available, preselected or [])
    except Exception as e:
        print(f"⚠️ No se pudo cargar la interfaz TUI ({e}).")
        return []

def select_parent_items_interactively(inherited_repo: MOMInheritedRepository, current_phase: ESAPhase, preselected: Optional[List[str]] = None) -> List[str]:
    """Muestra un menú TUI navegable con ID y Título para seleccionar los parent_ids de un ítem atómico."""
    all_items = inherited_repo.list_all_consolidated()
    
    valid_parents = [
        f"{item.id} | [{item.phase.value.upper()}] {item.title}"
        for item in all_items.values()
    ]

    if not valid_parents:
        if current_phase not in (ESAPhase.COR, ESAPhase.URD):
            print("⚠️ No hay elementos padres disponibles. Debes crear primero un elemento en una fase previa (ej. COR o URD).")
        return []

    try:
        return curses.wrapper(_curses_multi_select, f"SELECCIÓN DE ELEMENTOS PADRES PARA FASE {current_phase.value.upper()}", valid_parents, preselected or [])
    except Exception as e:
        print(f"⚠️ No se pudo cargar la interfaz TUI ({e}).")
        return []

def menu_create_project(pm: ProjectManager) -> None:
    print("\n--- 📁 CREAR NUEVO PROYECTO MOM ---")
    name = input("Nombre del nuevo proyecto: ").strip()
    if not name:
        print("❌ El nombre no puede estar vacío.")
        return

    is_private = ask_confirmation("¿Este proyecto es PRIVADO? (Si es privado, se excluirá automáticamente en .gitignore)", default=False)
    parents = select_parent_projects_interactively(pm)
    target_docs = input("Ruta externa de exportación de docs (opcional, Enter para omitir): ").strip()

    print("\nResumen del nuevo proyecto:")
    print(f"  • Nombre: {name}")
    print(f"  • Visibilidad: {'🔒 PRIVADO (Excluido en .gitignore)' if is_private else '🌐 PÚBLICO (Rastreado en Git)'}")
    print(f"  • Padres (Herencia DAG): {parents if parents else 'Ninguno (Proyecto Raíz)'}")
    print(f"  • Ruta Target Docs: {target_docs if target_docs else 'Sin exportación externa'}")

    if ask_confirmation("¿Deseas crear el proyecto con estos datos?"):
        try:
            proj_dir = pm.create_project(name, parent_projects=parents, target_docs_dir=target_docs, is_private=is_private)
            print(f"✅ Proyecto '{name}' creado con éxito en: {proj_dir}")
        except Exception as e:
            print(f"❌ Error al crear proyecto: {e}")
    else:
        print("🛑 Operación cancelada por el usuario.")

def menu_configure_project(pm: ProjectManager) -> None:
    print("\n--- ⚙️ CONFIGURAR PROYECTO (VISIBILIDAD, HERENCIA Y RUTA TARGET) ---")
    projects = [p.name for p in pm.data_dir.iterdir() if p.is_dir() and (p / "project.json").exists()]
    if not projects:
        print("❌ No hay proyectos registrados.")
        return

    print("Selecciona el proyecto a configurar:")
    for i, p in enumerate(projects, 1):
        print(f"  [{i}] {p}")

    try:
        idx = int(input("Selecciona el número de proyecto: ")) - 1
        target_project = projects[idx]
    except (ValueError, IndexError):
        print("❌ Selección no válida.")
        return

    proj_json = pm.data_dir / target_project / "project.json"
    with open(proj_json, "r", encoding="utf-8") as f:
        meta = json.load(f)

    current_parents = meta.get("parent_projects", [])
    current_target = meta.get("target_docs_dir", "")
    current_private = meta.get("is_private", False)

    print(f"\nConfiguración actual de '{target_project}':")
    print(f"  • Visibilidad: {'🔒 PRIVADO' if current_private else '🌐 PÚBLICO'}")
    print(f"  • Padres: {current_parents if current_parents else 'Ninguno'}")
    print(f"  • Ruta Target Docs: {current_target if current_target else 'Sin configurar'}")

    print("\n¿Qué deseas modificar?")
    print("  [1] Cambiar visibilidad (Público / Privado en .gitignore)")
    print("  [2] Modificar proyectos padres (Herencia DAG)")
    print("  [3] Modificar ruta target de exportación de docs")
    print("  [0] Cancelar")

    opt = input("Opción [0-3]: ").strip()
    if opt == "1":
        new_private = not current_private
        meta["is_private"] = new_private
        pm.sync_gitignore_privacy(target_project, new_private)
        status_str = "🔒 PRIVADO (regla añadida a .gitignore)" if new_private else "🌐 PÚBLICO (regla eliminada de .gitignore)"
        print(f"ℹ️ Visibilidad ajustada a: {status_str}")
    elif opt == "2":
        new_parents = select_parent_projects_interactively(pm, exclude_project=target_project, preselected=current_parents)
        meta["parent_projects"] = new_parents
    elif opt == "3":
        new_target = input("Introduce la nueva ruta target (o pulsa Enter para limpiar/desactivar): ").strip()
        meta["target_docs_dir"] = new_target
    else:
        print("🛑 Cancelado.")
        return

    if ask_confirmation("¿Guardar los cambios de configuración en project.json?"):
        with open(proj_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        print("✅ Configuración del proyecto actualizada.")

def menu_create_item(pm: ProjectManager) -> None:
    print("\n--- 📝 CREAR / EDITAR ESPECIFICACIÓN ATÓMICA (JSON) ---")
    projects = [p.name for p in pm.data_dir.iterdir() if p.is_dir() and (p / "project.json").exists()]
    if not projects:
        print("❌ No hay proyectos creados. Crea un proyecto primero.")
        return

    print("Proyectos disponibles:")
    for i, p in enumerate(projects, 1):
        print(f"  [{i}] {p}")
    
    try:
        idx = int(input("Selecciona el número de proyecto: ")) - 1
        target_project = projects[idx]
    except (ValueError, IndexError):
        print("❌ Selección no válida.")
        return

    inherited_repo = MOMInheritedRepository(pm, target_project)
    repo = MOMRepository(pm.data_dir / target_project)

    print("\nFases ESA/MOM disponibles: [0] COR  [1] URD  [2] SRD  [3] ADD  [4] DDD")
    phase_map = {"0": ESAPhase.COR, "1": ESAPhase.URD, "2": ESAPhase.SRD, "3": ESAPhase.ADD, "4": ESAPhase.DDD}
    p_choice = input("Selecciona la fase [0-4]: ").strip()
    if p_choice not in phase_map:
        print("❌ Fase no válida.")
        return
    phase = phase_map[p_choice]

    item_id = input(f"ID del ítem (debe empezar con '{phase.value.upper()}-', ej. {phase.value.upper()}-CORE-001): ").strip()
    title = input("Título del elemento: ").strip()
    description = input("Descripción detallada del requisito / axioma / diseño: ").strip()

    parent_ids: List[str] = []
    if phase not in (ESAPhase.COR, ESAPhase.URD):
        print("\nSelecciona los elementos padres de los que hereda este ítem:")
        parent_ids = select_parent_items_interactively(inherited_repo, current_phase=phase)
    elif phase == ESAPhase.URD:
        if ask_confirmation("¿Deseas vincular este URD con algún axioma del CORPUS o elemento existente?", default=False):
            parent_ids = select_parent_items_interactively(inherited_repo, current_phase=phase)

    is_user_doc = ask_confirmation("¿Este elemento debe incluirse en el Manual de Usuario u Onboarding?")
    guardrails = input("AI Guardrails / Instrucciones inmutables para la IA (opcional): ").strip() or None

    print("\nPreview de la especificación atómica:")
    print(f"  • ID: {item_id}")
    print(f"  • Fase: {phase.value.upper()}")
    print(f"  • Título: {title}")
    print(f"  • Padres: {parent_ids if parent_ids else 'Ninguno'}")
    print(f"  • Doc Usuario: {is_user_doc}")
    print(f"  • Guardrails: {guardrails if guardrails else 'Ninguno'}")

    if ask_confirmation("¿Confirmas la escritura de este fichero JSON atómico en el disco?"):
        try:
            item = MOMItem(
                id=item_id,
                phase=phase,
                title=title,
                description=description,
                parent_ids=parent_ids,
                attributes=ItemAttributes(priority=PriorityEnum.HIGH, is_user_doc=is_user_doc),
                metadata=ItemMetadata(author="Metsuke", declared_in_project=target_project, ai_guardrails=guardrails)
            )
            repo.create_item(item)
            print(f"✅ Ítem '{item_id}' guardado correctamente en {target_project}.")
        except Exception as e:
            print(f"❌ Error al guardar el ítem: {e}")
    else:
        print("🛑 Escritura cancelada.")

def menu_compile_project(pm: ProjectManager) -> None:
    print("\n--- ⚙️ COMPILACIÓN DE DOCUMENTACIÓN ---")
    projects = [p.name for p in pm.data_dir.iterdir() if p.is_dir() and (p / "project.json").exists()]
    if not projects:
        print("❌ No hay proyectos para compilar.")
        return

    print("Selecciona el proyecto a compilar:")
    for i, p in enumerate(projects, 1):
        print(f"  [{i}] {p}")
    
    try:
        idx = int(input("Selecciona número: ")) - 1
        target_project = projects[idx]
    except (ValueError, IndexError):
        print("❌ Selección no válida.")
        return

    print(f"\nCompilando proyecto '{target_project}' y resolviendo árbol de herencia DAG...")
    repo = MOMInheritedRepository(pm, target_project)
    compiler = MOMCompiler(repo)

    errors = compiler.validate_graph()
    if errors:
        print("❌ Se han detectado errores en la trazabilidad ESA/MOM del proyecto:")
        for err in errors:
            print(f"  • {err}")
        print("🛑 Compilación abortada por fallos de trazabilidad.")
        return

    print("✅ Grafo ESA/MOM 100% válido y verificado.")
    if repo.target_docs_dir:
        print(f"📦 Se exportará automáticamente una copia a: {repo.target_docs_dir}")
    else:
        print("ℹ️ Sin exportación externa configurada (solo compilación local).")

    if ask_confirmation(f"¿Proceder a compilar '{target_project}'?"):
        compiler.compile_all()
        print(f"✅ Compilación completada con éxito para '{target_project}'.")
    else:
        print("🛑 Compilación cancelada.")

def menu_review_agent_proposal(pm: ProjectManager) -> None:
    print("\n--- 🤖 REVISIÓN Y APROBACIÓN DE PROPUESTAS PENDIENTES DE IA ---")
    proposals_dir = pm.ai_proposals_dir
    proposal_files = list(proposals_dir.glob("*.json"))

    if not proposal_files:
        print("ℹ️ No hay propuestas pendientes de IA en 'data/ai-proposals/'.")
        return

    proposals_by_project: Dict[str, List[Path]] = {}
    for pf in proposal_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                data = json.load(f)
            proj = data.get("metadata", {}).get("declared_in_project", "Sin_Proyecto")
            proposals_by_project.setdefault(proj, []).append(pf)
        except Exception:
            proposals_by_project.setdefault("Errores_Parsing", []).append(pf)

    for proj in proposals_by_project:
        proposals_by_project[proj].sort(key=lambda p: p.stat().st_mtime)

    print("Proyectos con propuestas pendientes de revisión (orden cronológico FIFO):")
    projects_list = list(proposals_by_project.keys())
    for i, proj in enumerate(projects_list, 1):
        count = len(proposals_by_project[proj])
        print(f"  [{i}] Proyecto '{proj}' ({count} propuesta/s pendiente/s)")

    try:
        idx = int(input("\nSelecciona el proyecto a revisar: ")) - 1
        target_proj = projects_list[idx]
    except (ValueError, IndexError):
        print("❌ Selección no válida.")
        return

    selected_files = proposals_by_project[target_proj]
    print(f"\n--- Revisando {len(selected_files)} propuesta/s para el proyecto '{target_proj}' en ORDEN CRONOLÓGICO ---")

    for pf in selected_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                data = json.load(f)
            item = MOMItem.from_dict(data)
        except Exception as e:
            print(f"❌ Error leyendo la propuesta {pf.name}: {e}")
            continue

        timestamp = datetime.datetime.fromtimestamp(pf.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')

        print("\n-------------------------------------------------------")
        print(f"📄 Archivo Propuesta: {pf.name}")
        print(f"🕒 Fecha de Propuesta: {timestamp}")
        print(f"  • ID Elemento: {item.id}")
        print(f"  • Fase: {item.phase.value.upper()}")
        print(f"  • Título: {item.title}")
        print(f"  • Descripción:\n    {item.description}")
        print(f"  • Guardrails: {item.metadata.ai_guardrails}")
        print("-------------------------------------------------------")

        if ask_confirmation("¿APROBAR e integrar esta propuesta en el proyecto?"):
            repo = MOMRepository(pm.data_dir / target_proj)
            try:
                repo.update_item(item) if repo.read_item(item.id) else repo.create_item(item)
                pf.unlink()
                print(f"✅ Propuesta '{item.id}' APROBADA e integrada. Archivo de propuesta eliminado.")
            except Exception as e:
                print(f"❌ Error al integrar la propuesta: {e}")
        else:
            if ask_confirmation("¿Deseas RECHAZAR y ELIMINAR esta propuesta del disco?"):
                pf.unlink()
                print("🗑️ Propuesta rechazada y descartada.")
            else:
                print("⏸️ Propuesta mantenida en 'data/ai-proposals/' para revisión posterior.")

def interactive_main() -> None:
    pm = ProjectManager()
    while True:
        print("\n=======================================================")
        print("     MOM (MetsuOS Methodology) - MENÚ PRINCIPAL       ")
        print("=======================================================")
        print("  [1] Listar proyectos y estado de la herencia")
        print("  [2] Crear un nuevo proyecto")
        print("  [3] Configurar proyecto (Visibilidad, Herencia y Ruta Target)")
        print("  [4] Crear / Editar especificación atómica (JSON)")
        print("  [5] Compilar proyecto (Generar doc. MD, Vault Obsidian y AGENTS.md)")
        print("  [6] Revisar y aprobar/rechazar propuestas de IA (data/ai-proposals/)")
        print("  [0] Salir")
        print("-------------------------------------------------------")
        choice = input("Selecciona una opción [0-6]: ").strip()

        if choice == "1":
            print("\n📋 Proyectos registrados:")
            projs = [p for p in pm.data_dir.iterdir() if p.is_dir() and (p / "project.json").exists()]
            if not projs:
                print("  (Aún no hay proyectos registrados. Crea uno con la opción [2])")
            for p in projs:
                chain = pm.get_inheritance_chain(p.name)
                proj_json = p / "project.json"
                target_str = ""
                vis_str = "🌐 Público"
                if proj_json.exists():
                    with open(proj_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data.get("is_private", False):
                            vis_str = "🔒 Privado"
                        t_raw = data.get("target_docs_dir", "").strip()
                        if t_raw:
                            target_str = f" | Target Docs: {t_raw}"
                print(f"  • {p.name} [{vis_str}] (Cadena DAG: {' -> '.join(chain)}{target_str})")
        elif choice == "2":
            menu_create_project(pm)
        elif choice == "3":
            menu_configure_project(pm)
        elif choice == "4":
            menu_create_item(pm)
        elif choice == "5":
            menu_compile_project(pm)
        elif choice == "6":
            menu_review_agent_proposal(pm)
        elif choice == "0":
            print("\n👋 Saliendo de MOM. ¡Soberanía y control garantizados!")
            break
        else:
            print("⚠️ Opción no válida. Por favor introduce un número entre 0 y 6.")

def main() -> None:
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(description="MOM Standalone CLI")
        subparsers = parser.add_subparsers(dest="command")
        proj_parser = subparsers.add_parser("projects", help="Gestión de proyectos")
        proj_parser.add_argument("--action", choices=["list", "create"], required=True)
        proj_parser.add_argument("--name", help="Nombre")
        proj_parser.add_argument("--parents", help="Padres separados por coma")
        
        compile_parser = subparsers.add_parser("compile", help="Compilación")
        compile_parser.add_argument("--project", required=True)

        args = parser.parse_args()
        pm = ProjectManager()
        if args.command == "projects":
            if args.action == "list":
                for p in pm.data_dir.iterdir():
                    if p.is_dir() and (p / "project.json").exists():
                        print(f"  - {p.name}")
            elif args.action == "create":
                parents = [p.strip() for p in args.parents.split(",")] if args.parents else []
                pm.create_project(args.name, parent_projects=parents)
                print(f"✅ Proyecto '{args.name}' creado.")
        elif args.command == "compile":
            repo = MOMInheritedRepository(pm, args.project)
            compiler = MOMCompiler(repo)
            if not compiler.validate_graph():
                compiler.compile_all()
                print(f"✅ Proyecto '{args.project}' compilado.")
    else:
        interactive_main()

if __name__ == "__main__":
    main()

# Version: 0.4.0