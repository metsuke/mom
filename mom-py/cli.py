import sys
import json
import argparse
from pathlib import Path
from typing import Optional, List
from mom.projects import ProjectManager, MOMInheritedRepository
from mom.compiler import MOMCompiler
from mom.crud import MOMRepository
from mom.schemas import MOMItem, ESAPhase, PriorityEnum, StatusEnum, VerificationMethod, ItemAttributes, ItemMetadata

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

def menu_create_project(pm: ProjectManager) -> None:
    print("\n--- 📁 CREAR NUEVO PROYECTO MOM ---")
    name = input("Nombre del nuevo proyecto: ").strip()
    if not name:
        print("❌ El nombre no puede estar vacío.")
        return

    parents_raw = input("Proyectos padres de los que hereda (separados por coma, o Enter para ninguno): ").strip()
    parents = [p.strip() for p in parents_raw.split(",") if p.strip()] if parents_raw else []

    print("\nResumen del nuevo proyecto:")
    print(f"  • Nombre: {name}")
    print(f"  • Padres (Herencia DAG): {parents if parents else 'Ninguno (Proyecto Raíz)'}")

    if ask_confirmation("¿Deseas crear las carpetas y el proyecto con estos datos?"):
        try:
            proj_dir = pm.create_project(name, parent_projects=parents)
            print(f"✅ Proyecto '{name}' creado con éxito en: {proj_dir}")
        except Exception as e:
            print(f"❌ Error al crear proyecto: {e}")
    else:
        print("🛑 Operación cancelada por el usuario.")

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

    repo = MOMRepository(pm.data_dir / target_project)

    print("\nFases ESA PSS-05 disponibles: [1] URD  [2] SRD  [3] ADD  [4] DDD")
    phase_map = {"1": ESAPhase.URD, "2": ESAPhase.SRD, "3": ESAPhase.ADD, "4": ESAPhase.DDD}
    p_choice = input("Selecciona la fase [1-4]: ").strip()
    if p_choice not in phase_map:
        print("❌ Fase no válida.")
        return
    phase = phase_map[p_choice]

    item_id = input(f"ID del ítem (debe empezar con '{phase.value.upper()}-', ej. {phase.value.upper()}-CORE-001): ").strip()
    title = input("Título del elemento: ").strip()
    description = input("Descripción detallada del requisito / diseño: ").strip()

    parents_raw = input("IDs de elementos padres (parent_ids separados por coma, obligatorio si no es URD): ").strip()
    parent_ids = [p.strip() for p in parents_raw.split(",") if p.strip()] if parents_raw else []

    is_user_doc = ask_confirmation("¿Este elemento debe incluirse en el Manual de Usuario u Onboarding?")
    guardrails = input("AI Guardrails / Instrucciones inmutables para la IA (opcional): ").strip() or None

    print("\nPreview de la especificación atómica:")
    print(f"  • ID: {item_id}")
    print(f"  • Fase: {phase.value.upper()}")
    print(f"  • Título: {title}")
    print(f"  • Padres: {parent_ids}")
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
    print("\n--- ⚙️ COMPILACIÓN Y DESPLIEGUE DE DOCUMENTACIÓN ---")
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

    target_docs = input("Ruta de carpeta 'docs/' de destino externo (opcional, pulsa Enter para omitir): ").strip() or None
    target_path = Path(target_docs) if target_docs else None

    print(f"\nCompilando proyecto '{target_project}' y resolviendo árbol de herencia DAG...")
    repo = MOMInheritedRepository(pm, target_project)
    compiler = MOMCompiler(repo, target_docs_dir=target_path)

    errors = compiler.validate_graph()
    if errors:
        print("❌ Se han detectado errores en la trazabilidad ESA del proyecto:")
        for err in errors:
            print(f"  • {err}")
        print("🛑 Compilación abortada por fallos de trazabilidad.")
        return

    print("✅ Grafo ESA 100% válido y verificado.")
    if ask_confirmation(f"¿Proceder a generar doc/*.md, vault/ de Obsidian y AGENTS.md en '{target_project}'?"):
        compiler.compile_all()
        print(f"✅ Compilación completada con éxito para '{target_project}'.")
        if target_path:
            print(f"📦 Entregables desplegados en: {target_path}")
    else:
        print("🛑 Compilación cancelada.")

def menu_review_agent_proposal(pm: ProjectManager) -> None:
    print("\n--- 🤖 REVISIÓN Y APROBACIÓN MANUAL DE CAMBIOS PROPUESTOS POR IA ---")
    file_path_raw = input("Ruta al archivo JSON propuesto por el Agente de IA: ").strip()
    if not file_path_raw or not Path(file_path_raw).exists():
        print("❌ El archivo propuesto no existe.")
        return

    try:
        with open(file_path_raw, "r", encoding="utf-8") as f:
            proposal_data = json.load(f)
        item = MOMItem.from_dict(proposal_data)
    except Exception as e:
        print(f"❌ Error al parsear la propuesta de la IA: {e}")
        return

    print("\n🔍 DETALLES DE LA PROPUESTA DEL AGENTE DE IA:")
    print(f"  • ID Objetado/Propuesto: {item.id}")
    print(f"  • Fase: {item.phase.value.upper()}")
    print(f"  • Título: {item.title}")
    print(f"  • Descripción Propuesta:\n    {item.description}")
    print(f"  • Guardrails Inmutables: {item.metadata.ai_guardrails}")

    print("\n⚠️ NINGÚN CAMBIO PROPUESTO POR LA IA SE APLICA SIN CONFIRMACIÓN MANUAL.")
    if ask_confirmation("¿Apruebas manualmente esta modificación propuesta por la IA para su escritura definitiva?"):
        target_project = item.metadata.declared_in_project or input("Introduce el nombre del proyecto destino: ").strip()
        repo = MOMRepository(pm.data_dir / target_project)
        try:
            repo.update_item(item) if repo.read_item(item.id) else repo.create_item(item)
            print(f"✅ Cambio propuesto por la IA aprobado e integrado en '{target_project}'.")
        except Exception as e:
            print(f"❌ Error al integrar el cambio: {e}")
    else:
        print("🛑 Propuesta del Agente de IA RECHAZADA. No se ha modificado ningún archivo.")

def interactive_main() -> None:
    pm = ProjectManager()
    while True:
        print("\n=======================================================")
        print("     MOM (MetsuOS Methodology) - MENÚ PRINCIPAL       ")
        print("=======================================================")
        print("  [1] Listar proyectos y estado de la herencia")
        print("  [2] Crear un nuevo proyecto (con/sin herencia)")
        print("  [3] Crear / Editar especificación atómica (JSON)")
        print("  [4] Compilar proyecto (Generar doc. MD, Vault Obsidian y AGENTS.md)")
        print("  [5] Revisar y aprobar/rechazar propuesta de cambio de Agente IA")
        print("  [0] Salir")
        print("-------------------------------------------------------")
        choice = input("Selecciona una opción [0-5]: ").strip()

        if choice == "1":
            print("\n📋 Proyectos registrados:")
            for p in pm.data_dir.iterdir():
                if p.is_dir() and (p / "project.json").exists():
                    chain = pm.get_inheritance_chain(p.name)
                    print(f"  • {p.name} (Cadena DAG: {' -> '.join(chain)})")
        elif choice == "2":
            menu_create_project(pm)
        elif choice == "3":
            menu_create_item(pm)
        elif choice == "4":
            menu_compile_project(pm)
        elif choice == "5":
            menu_review_agent_proposal(pm)
        elif choice == "0":
            print("\n👋 Saliendo de MOM. ¡Soberanía y control garantizados!")
            break
        else:
            print("⚠️ Opción no válida. Por favor introduce un número entre 0 y 5.")

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
        compile_parser.add_argument("--target-docs", help="Ruta target")

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
            compiler = MOMCompiler(repo, target_docs_dir=Path(args.target_docs) if args.target_docs else None)
            if not compiler.validate_graph():
                compiler.compile_all()
                print(f"✅ Proyecto '{args.project}' compilado.")
    else:
        interactive_main()

if __name__ == "__main__":
    main()

# Version: 0.2.0