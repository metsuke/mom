import sys
import json
import re
import curses
import argparse
import datetime
import hashlib
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from projects import MOMProjectManager as ProjectManager, MOMInheritedRepository
from compiler import MOMCompiler
from schemas import MOMItem, ESAPhase, PriorityEnum, StatusEnum, VerificationMethod, ItemAttributes, ItemMetadata, CURRENT_SCHEMA_VERSION


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

        max_y, max_x = stdscr.getmaxyx()
        visible_rows = max_y - 5

        for idx, option in enumerate(options[:visible_rows]):
            y = idx + 4
            prefix = "[X] " if selected[idx] else "[ ] "
            if idx == current_idx:
                stdscr.addstr(y, 2, f"> {prefix}{option}"[:max_x-3], curses.A_REVERSE)
            else:
                stdscr.addstr(y, 2, f"  {prefix}{option}"[:max_x-3])

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
    """Obtiene proyectos clasificados por categoría (Core, Obras/Autores, Patentes, Auditorías)."""
    available_dirs = [
        p.name for p in pm.projects_root.iterdir() 
        if p.is_dir() and (p / "project.json").exists() and p.name != exclude_project
    ]
    if not available_dirs:
        print("ℹ️ No hay otros proyectos disponibles de los que heredar.")
        return []

    categorized = []
    for proj_id in sorted(available_dirs):
        if proj_id.startswith("AUTHOR-"):
            cat = "[📚 OBRA / AUTOR]"
        elif proj_id.startswith("PATENT-") or proj_id == "MOSPAT":
            cat = "[⚖️ PATENTE]"
        elif proj_id.startswith("AUDIT-") or proj_id == "MOSAUDIT":
            cat = "[🛡️ AUDITORÍA]"
        else:
            cat = "[🏛️ CORE MOM]"
        categorized.append(f"{proj_id} | {cat}")

    try:
        return curses.wrapper(_curses_multi_select, "SELECCIÓN DE HERENCIA DE PROYECTOS CATEGORIZADA", categorized, preselected or [])
    except Exception as e:
        print(f"⚠️ No se pudo cargar la interfaz TUI ({e}).")
        return []


def select_parent_items_interactively(inherited_repo: MOMInheritedRepository, current_phase: ESAPhase, preselected: Optional[List[str]] = None) -> List[str]:
    """Muestra un menú TUI navegable con ID y Título para seleccionar los parent_ids de un ítem atómico."""
    all_items = inherited_repo.list_all_consolidated()
    
    valid_parents = []
    for item in all_items.values():
        origin_proj = item.metadata.declared_in_project or "DESCONOCIDO"
        valid_parents.append(f"{item.id} | [{item.phase.value.upper()}] ({origin_proj}) {item.title}")

    if not valid_parents:
        print("ℹ️ No hay elementos padres disponibles en el repositorio.")
        return []

    try:
        return curses.wrapper(_curses_multi_select, f"SELECCIÓN DE ELEMENTOS PADRES PARA FASE {current_phase.value.upper()}", valid_parents, preselected or [])
    except Exception as e:
        print(f"⚠️ No se pudo cargar la interfaz TUI ({e}).")
        return []


def get_next_auto_id(inherited_repo: MOMInheritedRepository, phase: ESAPhase, project_id: str, raw_input_id: str) -> str:
    """Calcula y asigna el siguiente número disponible correlativo si el ID introducido no termina en número."""
    clean_id = raw_input_id.strip().upper()
    
    if re.search(r'-\d{3,}$', clean_id):
        return clean_id

    prefix = clean_id.rstrip('-')
    if not prefix:
        prefix = f"{phase.value.upper()}-{project_id}"

    all_items = inherited_repo.list_all_consolidated()
    existing_numbers = []

    pattern = re.compile(rf'^{re.escape(prefix)}-(\d+)$')
    for item_id in all_items.keys():
        match = pattern.match(item_id)
        if match:
            existing_numbers.append(int(match.group(1)))

    next_num = max(existing_numbers) + 1 if existing_numbers else 1
    return f"{prefix}-{next_num:03d}"


def _calculate_sha256(file_path: Path) -> str:
    """Calcula el hash SHA-256 de un archivo local para verificación de integridad."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def execute_sovereign_git_push(repo_root: Path, commit_msg: str) -> bool:
    """Ejecuta atómicamente: git add . -> git commit -m ... -> git push origin main --force"""
    try:
        print("\n🚀 [GIT SOBERANO] Agregando archivos al índice local...")
        subprocess.run(["git", "-C", str(repo_root), "add", "."], check=True)

        print(f"📝 [GIT SOBERANO] Creando commit...")
        res_commit = subprocess.run(["git", "-C", str(repo_root), "commit", "-m", commit_msg], capture_output=True, text=True)
        if res_commit.returncode != 0 and "nothing to commit" in res_commit.stdout.lower():
            print("ℹ️ [GIT SOBERANO] No hay cambios pendientes para commit.")

        print("⚡ [GIT SOBERANO] Ejecutando sincronización forzada hacia remoto (git push origin main --force)...")
        subprocess.run(["git", "-C", str(repo_root), "push", "origin", "main", "--force"], check=True)
        print("✅ [GIT SOBERANO] Sincronización soberana completada con éxito en remoto.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ [GIT SOBERANO] Fallo en la ejecución del comando Git: {e}")
        return False


def menu_git_sovereign_sync() -> None:
    """Menú de sincronización soberana directa desde la CLI."""
    repo_root = current_dir.parent
    print("\n=======================================================")
    print(" ⚡ SINCRONIZACIÓN SOBERANA GIT (COMMIT & FORCE PUSH)")
    print("=======================================================")
    print("Escribe o pega tu mensaje de commit multilínea.")
    print("Para FINALIZAR y confirmar, escribe 'END' o 'EOF' en una línea nueva:\n")
    
    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() in ["END", "EOF"]:
                break
            lines.append(line)
        except EOFError:
            break

    commit_msg = "\n".join(lines).strip()
    if not commit_msg:
        print("❌ El mensaje de commit no puede estar vacío.")
        return

    print("\n------------------- Mensaje Registrado -------------------")
    print(commit_msg)
    print("----------------------------------------------------------\n")

    if ask_confirmation("¿Ejecutar git add . + commit + push --force a main con este mensaje?"):
        execute_sovereign_git_push(repo_root, commit_msg)


def _untrack_and_purge_private_path(root_dir: Path, relative_path: str) -> None:
    """Desindexa y purga rutas privadas de Git."""
    clean_path = relative_path.strip("/")
    purged_any = False
    
    try:
        check_cmd = ["git", "-C", str(root_dir), "ls-files", "--error-unmatch", clean_path]
        res = subprocess.run(check_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0:
            rm_cmd = ["git", "-C", str(root_dir), "rm", "-r", "--cached", clean_path]
            subprocess.run(rm_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  🧹 [GIT UNTRACK] Sacado del índice de Git: {clean_path}")
            purged_any = True
    except Exception as e:
        print(f"  ⚠️ Error desindexando '{clean_path}': {e}")

    try:
        log_cmd = ["git", "-C", str(root_dir), "log", "-1", "--format=%h", "--", clean_path]
        res_log = subprocess.run(log_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res_log.stdout.strip():
            print(f"  🚨 [PURGA DE HISTORIAL] Purgando historial de Git para {clean_path}...")
            if shutil.which("git-filter-repo"):
                purge_cmd = ["git", "-C", str(root_dir), "filter-repo", "--invert-paths", "--path", clean_path, "--force"]
            else:
                purge_cmd = [
                    "git", "-C", str(root_dir), "filter-branch", "--force",
                    "--index-filter", f"git rm -rf --cached --ignore-unmatch {clean_path}",
                    "--prune-empty", "--tag-name-filter", "cat", "--", "--all"
                ]
            subprocess.run(purge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            purged_any = True
    except Exception as e:
        print(f"  ⚠️ Error purgando historial de '{clean_path}': {e}")

    if purged_any:
        print("  ⚡ [PURGA AUTOMÁTICA] Sincronizando árbol limpio con remoto...")
        execute_sovereign_git_push(root_dir, f"fix(security): purga soberana de rastro privado de {clean_path}")


def append_to_root_gitignore(repo_root: Path, rule: str) -> None:
    """Añade una regla al .gitignore de la raíz del repositorio."""
    root_gitignore = repo_root / ".gitignore"
    rule_clean = rule.strip()
    
    lines = []
    if root_gitignore.exists():
        with open(root_gitignore, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines()]
            
    if rule_clean not in lines:
        with open(root_gitignore, "a", encoding="utf-8") as f:
            f.write(f"\n{rule_clean}\n")


def refresh_all_gitignores(pm: ProjectManager) -> None:
    """Aisla y verifica todos los proyectos privados en Git."""
    repo_root = current_dir.parent
    
    data_gitignore = repo_root / "data" / ".gitignore"
    if data_gitignore.exists():
        try:
            subprocess.run(["git", "-C", str(repo_root), "rm", "-f", "data/.gitignore"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            data_gitignore.unlink(missing_ok=True)
        except Exception:
            pass

    if not pm.projects_root.exists():
        return

    append_to_root_gitignore(repo_root, "data/library/")
    append_to_root_gitignore(repo_root, "data/ai-proposals/*.json")
    
    _untrack_and_purge_private_path(repo_root, "data/library/")
    _untrack_and_purge_private_path(repo_root, "data/ai-proposals/")

    for proj_dir in sorted(pm.projects_root.iterdir()):
        if proj_dir.is_dir() and (proj_dir / "project.json").exists():
            try:
                with open(proj_dir / "project.json", "r", encoding="utf-8") as f:
                    meta = json.load(f)
                
                if meta.get("is_private", False):
                    rel_path = f"data/projects/{proj_dir.name}/"
                    append_to_root_gitignore(repo_root, rel_path)
                    _untrack_and_purge_private_path(repo_root, rel_path)
            except Exception:
                pass


def _ensure_project_exists(pm: ProjectManager, proj_id: str, name: str, parents: List[str], is_private: bool, desc: str) -> None:
    """Crea o actualiza un nodo de proyecto en disco."""
    proj_dir = pm.projects_root / proj_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "specs").mkdir(exist_ok=True)

    json_path = proj_dir / "project.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        curr_parents = meta.get("parents", [])
        for p in parents:
            if p not in curr_parents:
                curr_parents.append(p)
        meta["parents"] = curr_parents
        meta["is_private"] = is_private
    else:
        meta = {
            "project_id": proj_id,
            "name": name,
            "phase": "COR",
            "parents": parents,
            "is_private": is_private,
            "mandatory": False,
            "description": desc,
            "schema_version": CURRENT_SCHEMA_VERSION
        }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    if is_private:
        repo_root = current_dir.parent
        append_to_root_gitignore(repo_root, f"data/projects/{proj_id}/")
        _untrack_and_purge_private_path(repo_root, f"data/projects/{proj_id}/")


def menu_bib_management(data_dir: Path, pm: ProjectManager) -> None:
    """Gestión de la Biblioteca Privada (data/library/bib/) con Captura ULTRA."""
    bib_dir = data_dir / "library" / "bib"
    bib_dir.mkdir(parents=True, exist_ok=True)

    _ensure_project_exists(pm, "MOSBIB", "Pilar Global de Bibliografía", [], False, "Pilar herencial de obras y fuentes bibliográficas")

    while True:
        print("\n=======================================================")
        print(" 📚 GESTIÓN DE BIBLIOTECA Y PROYECTOS OBRA (MOSBIB)")
        print("=======================================================")
        print("  [1] Registrar nuevo nodo Autor Consolidador (ej. AUTHOR-ESA)")
        print("  [2] Registrar nueva Obra / Matriz RAW (ej. AUTHOR-ESA-PSS05)")
        print("  [3] Extraer y despiezar obra (CAPTURA ULTRA - Modo Principal)")
        print("  [4] Trocear obra desde Markdown existente (Split Directo)")
        print("  [5] Ejecutar Kill-Switch / Revocación de Cita Literal")
        print("  [6] Eliminar obra bibliográfica registrada")
        print("  [0] Volver al Menú Principal")
        print("-------------------------------------------------------")

        opt = input("Selecciona una opción [0-6]: ").strip()

        if opt == "1":
            author_id = input("ID del Autor Consolidador (ej. AUTHOR-ESA): ").strip().upper()
            if not author_id.startswith("AUTHOR-"):
                author_id = f"AUTHOR-{author_id}"
            
            name = input(f"Nombre completo del Autor [{author_id}]: ").strip() or author_id
            desc = input("Descripción doctrinal del corpus del autor: ").strip()

            _ensure_project_exists(pm, author_id, name, ["MOSAUTHOR"], False, desc)
            (bib_dir / author_id).mkdir(parents=True, exist_ok=True)
            print(f"✅ Nodo Autor Consolidador '{author_id}' inicializado con éxito.")

        elif opt == "2":
            author_dirs = [d.name for d in pm.projects_root.iterdir() if d.is_dir() and d.name.startswith("AUTHOR-") and len(d.name.split("-")) == 2]
            if not author_dirs:
                print("❌ No hay nodos autor consolidador. Inicializa un nodo autor primero (opción 1).")
                continue

            print("Autores disponibles:")
            for i, a in enumerate(author_dirs, 1):
                print(f"  [{i}] {a}")
            
            try:
                a_idx = int(input("Selecciona Autor: ")) - 1
                parent_author_id = author_dirs[a_idx]
            except (ValueError, IndexError):
                print("❌ Selección no válida.")
                continue

            work_code = input("ID corto de la obra (ej. PSS05): ").strip().upper()
            work_project_id = f"{parent_author_id}-{work_code}"
            raw_project_id = f"{work_project_id}-RAW"

            title = input("Título completo de la obra: ").strip()
            publisher = input("Editorial / Entidad Emisora: ").strip()
            year_raw = input("Año de publicación: ").strip()
            year = int(year_raw) if year_raw.isdigit() else 2026
            source_lang = input("Idioma de origen (ej. en, es, fr) [en]: ").strip().lower() or "en"
            allow_export = ask_confirmation("¿Permite exportación de texto literal completo (Dominio Público/Licencia Abierta)?")
            raw_is_private = not allow_export

            raw_file_str = input("Ruta al archivo original completo (opcional, Enter para omitir): ").strip()
            sha256_str = ""

            _ensure_project_exists(pm, raw_project_id, f"Fuente Matriz RAW: {title}", [], raw_is_private, f"Archivo maestro original de {title}")
            _ensure_project_exists(pm, work_project_id, title, [raw_project_id], False, f"Despiece atómico de {title}")
            _ensure_project_exists(pm, "MOSBIB", "Pilar Global de Bibliografía", [work_project_id], False, "Pilar herencial de obras")
            _ensure_project_exists(pm, parent_author_id, parent_author_id, [work_project_id, "MOSBIB"], False, "Autor consolidador")

            work_dir = bib_dir / parent_author_id / work_code
            (work_dir / "raw").mkdir(parents=True, exist_ok=True)
            (work_dir / "split").mkdir(parents=True, exist_ok=True)

            if raw_file_str:
                raw_path = Path(raw_file_str).expanduser().resolve()
                if raw_path.exists():
                    dest_file = work_dir / "raw" / raw_path.name
                    shutil.copy(raw_path, dest_file)
                    sha256_str = _calculate_sha256(dest_file)
                    print(f"✅ Archivo origen copiado a la biblioteca privada. SHA-256: {sha256_str}")

            bib_meta = {
                "project_id": work_project_id,
                "raw_project_id": raw_project_id,
                "author_id": parent_author_id,
                "work_id": work_code,
                "title": title,
                "publisher": publisher,
                "year": year,
                "source_language": source_lang,
                "allow_full_text_export": allow_export,
                "kill_switch_enabled": False,
                "sha256_hash": sha256_str
            }

            with open(work_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(bib_meta, f, indent=2, ensure_ascii=False)

            print(f"✅ OBRA REGISTRADA: '{work_project_id}' (Idioma Origen: {source_lang})")

            if raw_file_str and ask_confirmation("¿Deseas lanzar la CAPTURA ULTRA e ingesta inmediatamente?"):
                from ingest_agent import MOMMultilingualIngestionAgent
                agent = MOMMultilingualIngestionAgent(data_dir=data_dir)
                res = agent.ingest_registered_work(work_dir, source_lang=source_lang)
                input("\n🔻 Presiona [Enter] para continuar...")

        elif opt == "3":
            print("\n--- ⚡ EXTRACCIÓN Y TROCEO CON CAPTURA ULTRA ---")
            author_dirs = [d for d in bib_dir.iterdir() if d.is_dir()]
            registered_works = []

            for ad in author_dirs:
                for wd in ad.iterdir():
                    if wd.is_dir() and (wd / "metadata.json").exists():
                        registered_works.append(wd)

            if not registered_works:
                print("❌ No hay obras registradas con metadata.json en la biblioteca.")
                input("\n🔻 Presiona [Enter] para continuar...")
                continue

            print("Obras disponibles para Captura ULTRA:")
            for i, wd in enumerate(registered_works, 1):
                with open(wd / "metadata.json", "r", encoding="utf-8") as f:
                    meta = json.load(f)
                print(f"  [{i}] {meta.get('author_id')} / {meta.get('work_id')} - {meta.get('title')} [{meta.get('source_language', 'en')}]")

            try:
                w_idx = int(input("\nSelecciona el número de obra a procesar: ")) - 1
                target_work_dir = registered_works[w_idx]
            except (ValueError, IndexError):
                print("❌ Selección no válida.")
                input("\n🔻 Presiona [Enter] para continuar...")
                continue

            with open(target_work_dir / "metadata.json", "r", encoding="utf-8") as f:
                meta = json.load(f)

            from ingest_agent import MOMMultilingualIngestionAgent
            agent = MOMMultilingualIngestionAgent(data_dir=data_dir)
            res = agent.ingest_registered_work(target_work_dir, source_lang=meta.get("source_language", "en"))
            input("\n🔻 Presiona [Enter] para continuar...")

        elif opt == "4":
            print("\n--- 📝 TROCEO DIRECTO DESDE MARKDOWN EXISTENTE ---")
            author_dirs = [d for d in bib_dir.iterdir() if d.is_dir()]
            registered_works = []

            for ad in author_dirs:
                for wd in ad.iterdir():
                    if wd.is_dir() and (wd / "metadata.json").exists():
                        registered_works.append(wd)

            if not registered_works:
                print("❌ No hay obras registradas en la biblioteca.")
                input("\n🔻 Presiona [Enter] para continuar...")
                continue

            print("Obras disponibles para troceo directo desde .md:")
            for i, wd in enumerate(registered_works, 1):
                with open(wd / "metadata.json", "r", encoding="utf-8") as f:
                    meta = json.load(f)
                print(f"  [{i}] {meta.get('author_id')} / {meta.get('work_id')} - {meta.get('title')}")

            try:
                w_idx = int(input("\nSelecciona el número de obra a procesar: ")) - 1
                target_work_dir = registered_works[w_idx]
            except (ValueError, IndexError):
                print("❌ Selección no válida.")
                input("\n🔻 Presiona [Enter] para continuar...")
                continue

            from ingest_agent import MOMMultilingualIngestionAgent
            agent = MOMMultilingualIngestionAgent(data_dir=data_dir)
            res = agent.ingest_registered_work_from_markdown(target_work_dir)
            input("\n🔻 Presiona [Enter] para continuar...")

        elif opt == "5":
            print("\n--- 🚨 EJECUCIÓN DE KILL-SWITCH / REVOCACIÓN DE DIFUSIÓN PÚBLICA ---")
            author_dirs = [d for d in bib_dir.iterdir() if d.is_dir()]
            all_works = []

            for ad in author_dirs:
                for wd in ad.iterdir():
                    if wd.is_dir() and (wd / "metadata.json").exists():
                        all_works.append(wd)

            if not all_works:
                print("❌ No hay obras registradas en la biblioteca.")
                continue

            print("Obras registradas:")
            for i, wd in enumerate(all_works, 1):
                print(f"  [{i}] {wd.parent.name} / {wd.name}")

            try:
                w_idx = int(input("Selecciona obra para modificar/revocar: ")) - 1
                target_work = all_works[w_idx]
            except (ValueError, IndexError):
                print("❌ Selección no válida.")
                continue

            meta_file = target_work / "metadata.json"
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            if ask_confirmation("¿Deseas ACTIVAR el Kill-Switch y REVOCAR inmediatamente la exportación pública?"):
                meta["allow_full_text_export"] = False
                meta["kill_switch_enabled"] = True
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2, ensure_ascii=False)
                
                raw_id = meta.get("raw_project_id")
                if raw_id:
                    raw_json = pm.projects_root / raw_id / "project.json"
                    if raw_json.exists():
                        with open(raw_json, "r", encoding="utf-8") as f:
                            rmeta = json.load(f)
                        rmeta["is_private"] = True
                        with open(raw_json, "w", encoding="utf-8") as f:
                            json.dump(rmeta, f, indent=2, ensure_ascii=False)

                repo_root = current_dir.parent
                execute_sovereign_git_push(repo_root, f"fix(security): activado kill-switch soberano para obra {meta.get('work_id')}")

        elif opt == "6":
            print("\n--- 🗑️ ELIMINAR OBRA BIBLIOGRÁFICA REGISTRADA ---")
            author_dirs = [d for d in bib_dir.iterdir() if d.is_dir()]
            all_works = []

            for ad in author_dirs:
                for wd in ad.iterdir():
                    if wd.is_dir() and (wd / "metadata.json").exists():
                        all_works.append(wd)

            if not all_works:
                print("❌ No hay obras registradas en la biblioteca.")
                continue

            print("Obras registradas:")
            for i, wd in enumerate(all_works, 1):
                print(f"  [{i}] {wd.parent.name} / {wd.name}")

            try:
                w_idx = int(input("Selecciona la obra a ELIMINAR: ")) - 1
                target_work = all_works[w_idx]
            except (ValueError, IndexError):
                print("❌ Selección no válida.")
                continue

            meta_file = target_work / "metadata.json"
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

            if ask_confirmation(f"¿⚠️ Estás COMPLETAMENTE SEGURO de eliminar la obra '{meta.get('title')}' y todos sus archivos del disco?"):
                shutil.rmtree(target_work, ignore_errors=True)
                print(f"✅ Obra '{meta.get('work_id')}' eliminada correctamente.")
                
        elif opt == "0":
            break


def menu_patent_management(data_dir: Path, pm: ProjectManager) -> None:
    """Gestión del Pilar MOSPAT y Registro de Patentes."""
    pat_dir = data_dir / "library" / "patents"
    pat_dir.mkdir(parents=True, exist_ok=True)

    _ensure_project_exists(pm, "MOSPAT", "Pilar Global de Patentes y FTO", [], False, "Pilar herencial de patentes")

    print("\n=======================================================")
    print(" ⚖️ GESTIÓN DE PATENTES Y FREEDOM TO OPERATE (MOSPAT)")
    print("=======================================================")
    print("  [1] Registrar Nueva Patente como PROYECTO FORMAL INDEPENDIENTE")
    print("  [2] Consultar Estado FTO y Expiración Territorial")
    print("  [0] Volver al Menú Principal")
    print("-------------------------------------------------------")

    opt = input("Selecciona una opción [0-2]: ").strip()

    if opt == "1":
        patent_code = input("Código de Patente (ej. US-123456): ").strip().upper()
        pat_project_id = f"PATENT-{patent_code}"
        raw_project_id = f"{pat_project_id}-RAW"

        title = input("Título / Objeto de la Patente: ").strip()
        jurisdiction = input("Jurisdicción Principal [US]: ").strip().upper() or "US"
        grant_year_raw = input("Año de Concesión: ").strip()
        grant_year = int(grant_year_raw) if grant_year_raw.isdigit() else 2010
        expiry_year = grant_year + 20

        claims_str = input("Resumen de Reivindicaciones Clave (Claims): ").strip()
        is_expired = datetime.datetime.now().year >= expiry_year
        is_private_raw = ask_confirmation("¿El documento original de patente es de uso privado?", default=False)

        _ensure_project_exists(pm, raw_project_id, f"Documento Matriz Patente: {title}", [], is_private_raw, f"Documento original de patente {patent_code}")
        _ensure_project_exists(pm, pat_project_id, f"Patente: {title}", [raw_project_id], False, f"FTO y Claims de {patent_code}")
        _ensure_project_exists(pm, "MOSPAT", "Pilar Global de Patentes", [pat_project_id], False, "Pilar herencial de patentes")

        p_folder = pat_dir / pat_project_id
        p_folder.mkdir(parents=True, exist_ok=True)

        meta_bib = {
            "patent_id": pat_project_id,
            "raw_project_id": raw_project_id,
            "title": title,
            "jurisdiction": jurisdiction,
            "grant_year": grant_year,
            "expiry_year_global": expiry_year,
            "is_expired": is_expired,
            "status": "EXPIRED" if is_expired else "ACTIVE",
            "claims_summary": claims_str
        }

        with open(p_folder / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta_bib, f, indent=2, ensure_ascii=False)

        print(f"✅ PATENTE REGISTRADA: '{pat_project_id}' ➔ MOSPAT")

    elif opt == "2":
        patents = [d for d in pat_dir.iterdir() if d.is_dir() and (d / "metadata.json").exists()]
        if not patents:
            print("ℹ️ No hay patentes registradas en MOSPAT.")
            return

        print("\nPatentes registradas:")
        for p in patents:
            with open(p / "metadata.json", "r", encoding="utf-8") as f:
                d = json.load(f)
            st_str = "🟢 EXPIRADA" if d.get("is_expired") else "🔴 ACTIVA (Restricción FTO)"
            print(f"  • {d.get('patent_id')}: {d.get('title')} [{st_str}] - Expiración: {d.get('expiry_year_global')}")


def menu_audit_management(data_dir: Path, pm: ProjectManager) -> None:
    """Gestión del Pilar MOSAUDIT y Auditoría de Código."""
    audit_dir = data_dir / "library" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    _ensure_project_exists(pm, "MOSAUDIT", "Pilar Global de Auditoría de Código", [], False, "Pilar herencial de auditorías")

    print("\n=======================================================")
    print(" 🛡️ AUDITORÍA DE CÓDIGO Y DECOMPILACIONES (MOSAUDIT)")
    print("=======================================================")
    print("  [1] Registrar Proyecto de Auditoría")
    print("  [2] Inspeccionar Discrepancias")
    print("  [0] Volver al Menú Principal")
    print("-------------------------------------------------------")

    opt = input("Selecciona una opción [0-2]: ").strip()

    if opt == "1":
        app_code = input("Código / ID de Aplicación (ej. APP-XYZ): ").strip().upper()
        audit_project_id = f"AUDIT-{app_code}"
        raw_project_id = f"{audit_project_id}-RAW"

        declared_repo = input("URL/Ruta del Repositorio Declarado: ").strip()
        binary_path_str = input("Ruta al Binario Ejecutable Decompilado (opcional): ").strip()
        is_private_raw = ask_confirmation("¿El binario/código original es PRIVADO?", default=True)

        _ensure_project_exists(pm, raw_project_id, f"Binarios RAW: {app_code}", [], is_private_raw, f"Binarios de {app_code}")
        _ensure_project_exists(pm, audit_project_id, f"Auditoría: {app_code}", [raw_project_id], False, f"Auditoría {app_code}")
        _ensure_project_exists(pm, "MOSAUDIT", "Pilar Global de Auditorías", [audit_project_id], False, "Pilar herencial de auditorías")

        app_dir = audit_dir / audit_project_id
        (app_dir / "declared").mkdir(parents=True, exist_ok=True)
        (app_dir / "decomp").mkdir(parents=True, exist_ok=True)

        sha256_str = ""
        if binary_path_str:
            bp = Path(binary_path_str).expanduser().resolve()
            if bp.exists():
                dest_bin = app_dir / "decomp" / bp.name
                shutil.copy(bp, dest_bin)
                sha256_str = _calculate_sha256(dest_bin)

        meta_bib = {
            "app_id": audit_project_id,
            "raw_project_id": raw_project_id,
            "declared_repo": declared_repo,
            "has_decompiled_binary": bool(binary_path_str),
            "sha256_hash": sha256_str,
            "audit_date": datetime.datetime.now().isoformat()
        }

        with open(app_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta_bib, f, indent=2, ensure_ascii=False)

        print(f"✅ AUDITORÍA REGISTRADA: '{audit_project_id}' ➔ MOSAUDIT")

    elif opt == "2":
        apps = [d for d in audit_dir.iterdir() if d.is_dir() and (d / "metadata.json").exists()]
        if not apps:
            print("ℹ️ No hay auditorías registradas.")
            return

        print("\nAuditorías en curso:")
        for a in apps:
            with open(a / "metadata.json", "r", encoding="utf-8") as f:
                d = json.load(f)
            print(f"  • {d.get('app_id')} | Hash SHA-256 Binario: {d.get('sha256_hash') or 'N/A'}")


def menu_configure_global_settings(data_dir: Path) -> None:
    """Gestiona la configuración global en data/config.json."""
    config_file = data_dir / "config.json"
    config = {
        "web_vault_dir": None, 
        "schema_version": CURRENT_SCHEMA_VERSION,
        "supervisor_name": "Humano Supervisor",
        "supervisor_email": "supervisor@metsuos.org",
        "supervisor_role": "Lead Audit Supervisor"
    }
    
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                config.update(loaded)
        except Exception:
            pass

    current_web = config.get("web_vault_dir")
    web_str = current_web if current_web else "🚫 DESACTIVADA"

    print("\n=======================================================")
    print(" ⚙️ CONFIGURACIÓN GLOBAL Y SUPERVISOR HUMANO")
    print("=======================================================")
    print(f"  • Ruta Web Vault:             {web_str}")
    print(f"  • Versión del Esquema Global: v{config.get('schema_version', CURRENT_SCHEMA_VERSION)}")
    print(f"  • Supervisor Humano a Cargo:  {config.get('supervisor_name')} <{config.get('supervisor_email')}>")
    print("-------------------------------------------------------")
    print("  [1] Configurar datos del Supervisor Humano")
    print("  [2] Configurar ruta Web Vault")
    print("  [3] Desactivar Web Vault")
    print("  [0] Volver al Menú Principal")
    print("-------------------------------------------------------")

    opt = input("Selecciona una opción [0-3]: ").strip()

    if opt == "1":
        s_name = input(f"Nombre Completo [{config.get('supervisor_name')}]: ").strip()
        if s_name:
            config["supervisor_name"] = s_name
        
        s_email = input(f"Email de Contacto [{config.get('supervisor_email')}]: ").strip()
        if s_email:
            config["supervisor_email"] = s_email

        s_role = input(f"Cargo [{config.get('supervisor_role')}]: ").strip()
        if s_role:
            config["supervisor_role"] = s_role

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print("✅ Configuración actualizada.")

    elif opt == "2":
        new_path = input("\nIntroduce la ruta hacia la carpeta web: ").strip()
        if new_path:
            p = Path(new_path).expanduser().resolve()
            config["web_vault_dir"] = str(p)
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"✅ Ruta de Web Vault configurada en: {p}")

    elif opt == "3":
        config["web_vault_dir"] = None
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print("✅ Exportación a Web Vault desactivada.")


def menu_create_project(pm: ProjectManager) -> Optional[str]:
    print("\n--- 📁 CREAR NUEVO PROYECTO MOM ---")
    project_id = input("ID del proyecto (ej. MOSCON): ").strip().upper()
    if not project_id:
        return None

    name = input("Nombre descriptivo: ").strip()
    if not name:
        return None

    phase = input("Fase ESA (COR, URD, SRD, ADD, DDD) [COR]: ").strip().upper() or "COR"
    is_private = ask_confirmation("¿Este proyecto es PRIVADO?", default=True)
    mandatory = ask_confirmation("¿Este proyecto es MANDATORIO?", default=True)
    description = input("Descripción: ").strip()

    parents = select_parent_projects_interactively(pm, exclude_project=project_id)

    if ask_confirmation("¿Deseas crear el proyecto?"):
        try:
            proj_dir = pm.projects_root / project_id
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "specs").mkdir(exist_ok=True)

            meta = {
                "project_id": project_id,
                "name": name,
                "phase": phase,
                "schema_version": CURRENT_SCHEMA_VERSION,
                "parents": parents,
                "is_private": is_private,
                "mandatory": mandatory,
                "default_decay_rate": 0.05,
                "language": "es-ES",
                "description": description
            }

            with open(proj_dir / "project.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            repo_root = current_dir.parent
            if is_private:
                append_to_root_gitignore(repo_root, f"data/projects/{project_id}/")
                _untrack_and_purge_private_path(repo_root, f"data/projects/{project_id}/")

            print(f"✅ Proyecto '{project_id}' creado.")
            return project_id
        except Exception as e:
            print(f"❌ Error al crear proyecto: {e}")
    return None


def menu_view_project_details(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
        if not projects:
            return
        try:
            idx = int(input("Selecciona número de proyecto: ")) - 1
            target_project = projects[idx]
        except (ValueError, IndexError):
            return

    proj_json = pm.projects_root / target_project / "project.json"
    if not proj_json.exists():
        return

    with open(proj_json, "r", encoding="utf-8") as f:
        meta = json.load(f)

    repo = MOMInheritedRepository(pm.projects_root, target_project)
    all_items = repo.list_all_consolidated()

    print("\n=======================================================")
    print(f" 📄 DATOS DEL PROYECTO: {target_project}")
    print("=======================================================")
    print(f"  • Nombre Completo: {meta.get('name', 'N/A')}")
    print(f"  • Visibilidad:     {'🔒 PRIVADO' if meta.get('is_private', True) else '🌐 PÚBLICO'}")
    print(f"  • Cadena Herencia: {' -> '.join(repo.chain)}")
    print(f"  • Ítems Totales:   {len(all_items)}")
    print("=======================================================")


def menu_configure_project(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
        if not projects:
            return
        try:
            idx = int(input("Selecciona el proyecto: ")) - 1
            target_project = projects[idx]
        except (ValueError, IndexError):
            return

    proj_json = pm.projects_root / target_project / "project.json"
    if not proj_json.exists():
        return

    with open(proj_json, "r", encoding="utf-8") as f:
        meta = json.load(f)

    current_parents = meta.get("parents", [])
    current_private = meta.get("is_private", True)

    print(f"\nConfiguración actual de '{target_project}':")
    print(f"  • Visibilidad: {'🔒 PRIVADO' if current_private else '🌐 PÚBLICO'}")
    print(f"  • Padres: {current_parents}")

    print("\n¿Qué deseas modificar?")
    print("  [1] Cambiar visibilidad")
    print("  [2] Modificar proyectos padres (Herencia DAG)")
    print("  [0] Cancelar")

    opt = input("Opción [0-2]: ").strip()
    if opt == "1":
        meta["is_private"] = not current_private
    elif opt == "2":
        meta["parents"] = select_parent_projects_interactively(pm, exclude_project=target_project, preselected=current_parents)
    else:
        return

    with open(proj_json, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print("✅ Configuración del proyecto actualizada.")


def menu_create_item(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
        if not projects:
            return
        try:
            idx = int(input("Selecciona proyecto: ")) - 1
            target_project = projects[idx]
        except (ValueError, IndexError):
            return

    inherited_repo = MOMInheritedRepository(pm.projects_root, target_project)

    print("\nFases ESA/MOM: [0] COR  [1] URD  [2] SRD  [3] ADD  [4] DDD")
    phase_map = {"0": ESAPhase.COR, "1": ESAPhase.URD, "2": ESAPhase.SRD, "3": ESAPhase.ADD, "4": ESAPhase.DDD}
    p_choice = input("Selecciona fase [0-4]: ").strip()
    if p_choice not in phase_map:
        return
    phase = phase_map[p_choice]

    raw_item_id = input(f"ID del ítem (ej. {phase.value.upper()}-{target_project}): ").strip()
    item_id = get_next_auto_id(inherited_repo, phase, target_project, raw_item_id)

    title = input("Título: ").strip()
    description = input("Descripción: ").strip()
    parent_ids = select_parent_items_interactively(inherited_repo, current_phase=phase)

    if ask_confirmation("¿Confirmas la escritura de esta especificación?"):
        item = MOMItem(
            id=item_id,
            phase=phase,
            title=title,
            description=description,
            parent_ids=parent_ids,
            attributes=ItemAttributes(priority=PriorityEnum.HIGH),
            metadata=ItemMetadata(author="Metsuke", declared_in_project=target_project)
        )
        inherited_repo.save_item(item)
        print(f"✅ Ítem '{item_id}' guardado.")


def menu_edit_item(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
        if not projects:
            return
        try:
            idx = int(input("Selecciona proyecto: ")) - 1
            target_project = projects[idx]
        except (ValueError, IndexError):
            return

    inherited_repo = MOMInheritedRepository(pm.projects_root, target_project)
    all_items = inherited_repo.list_all_consolidated()
    items_list = list(all_items.values())

    for i, it in enumerate(items_list, 1):
        print(f"  [{i}] {it.id} | [{it.phase.value.upper()}] {it.title}")

    try:
        sel_idx = int(input("\nSelecciona número de elemento a EDITAR: ")) - 1
        existing_item = items_list[sel_idx]
    except (ValueError, IndexError):
        return

    title_in = input(f"Título [{existing_item.title}]: ").strip()
    title = title_in if title_in else existing_item.title

    desc_in = input(f"Descripción [{existing_item.description}]: ").strip()
    description = desc_in if desc_in else existing_item.description

    parent_ids = select_parent_items_interactively(inherited_repo, current_phase=existing_item.phase, preselected=existing_item.parent_ids)

    if ask_confirmation("¿Guardar cambios?"):
        updated_item = MOMItem(
            id=existing_item.id,
            phase=existing_item.phase,
            title=title,
            description=description,
            parent_ids=parent_ids,
            attributes=existing_item.attributes,
            metadata=existing_item.metadata
        )
        inherited_repo.save_item(updated_item)
        print(f"✅ Ítem '{existing_item.id}' actualizado.")


def menu_compile_project(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
        if not projects:
            return
        try:
            idx = int(input("Selecciona proyecto: ")) - 1
            target_project = projects[idx]
        except (ValueError, IndexError):
            return

    repo = MOMInheritedRepository(pm.projects_root, target_project)
    compiler = MOMCompiler(repo)

    errors = compiler.validate_graph()
    if errors:
        for err in errors:
            print(f"  • {err}")
        return

    compiler.compile_all()
    print(f"✅ Compilación completada para '{target_project}'.")


def menu_compile_all_projects(pm: ProjectManager) -> None:
    projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
    for proj_name in projects:
        try:
            repo = MOMInheritedRepository(pm.projects_root, proj_name)
            compiler = MOMCompiler(repo)
            if not compiler.validate_graph():
                compiler.compile_all()
                print(f"✅ Proyecto '{proj_name}' compilado.")
        except Exception as e:
            print(f"❌ Error compilando '{proj_name}': {e}")


def menu_review_agent_proposal(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    proposals_dir = pm.projects_root.parent / "ai-proposals"
    proposal_files = list(proposals_dir.glob("*.json")) if proposals_dir.exists() else []

    if not proposal_files:
        print("ℹ️ No hay propuestas pendientes de IA.")
        return

    for pf in proposal_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                data = json.load(f)
            item = MOMItem.from_dict(data)
            proj = data.get("metadata", {}).get("declared_in_project", "MOSCON")

            print("\n-------------------------------------------------------")
            print(f"📄 Propuesta: {pf.name}")
            print(f"  • ID: {item.id} | Título: {item.title}")
            print(f"  • Texto:\n    {item.description}")
            print("-------------------------------------------------------")

            if ask_confirmation("¿APROBAR e integrar esta propuesta?"):
                repo = MOMInheritedRepository(pm.projects_root, proj)
                item.attributes.status = StatusEnum.APPROVED
                repo.save_item(item)
                pf.unlink()
                print(f"✅ Propuesta '{item.id}' aprobada e integrada.")
            elif ask_confirmation("¿RECHAZAR y eliminar esta propuesta?"):
                pf.unlink()
                print("🗑️ Propuesta eliminada.")
        except Exception as e:
            print(f"❌ Error procesando {pf.name}: {e}")


def select_active_project(pm: ProjectManager) -> Optional[str]:
    projs = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
    if not projs:
        return None

    for i, p in enumerate(projs, 1):
        print(f"  [{i}] {p}")

    try:
        idx = int(input("\nSelecciona proyecto activo: ")) - 1
        if 0 <= idx < len(projs):
            return projs[idx]
    except ValueError:
        pass
    return None


def interactive_main() -> None:
    projects_dir = current_dir.parent / "data" / "projects"
    data_dir = current_dir.parent / "data"
    pm = ProjectManager(projects_root=projects_dir)
    
    refresh_all_gitignores(pm)

    active_project: Optional[str] = "MOSCON" if (projects_dir / "MOSCON").exists() else None

    while True:
        act_str = f" [PROYECTO ACTIVO: {active_project}]" if active_project else " [NINGUNO SELECCIONADO]"
        print("\n=======================================================")
        print("     MOM (MetsuOS Methodology) - MENÚ PRINCIPAL       ")
        print(f"    {act_str}")
        print("=======================================================")
        print("  [1] Seleccionar / Cambiar proyecto activo")
        print("  [2] Crear un nuevo proyecto")
        print("  [3] Configurar proyecto (Visibilidad, Herencia y Metadatos)")
        print("  [4] Visualizar datos e inspeccionar proyecto activo")
        print("  [5] Crear NUEVA especificación atómica (JSON)")
        print("  [6] Editar especificación atómica EXISTENTE (JSON)")
        print("  [7] Compilar proyecto activo")
        print("  [8] Compilar TODOS los proyectos registrados")
        print("  [9] Revisar y aprobar/rechazar propuestas de IA")
        print("  [10] Gestión de Biblioteca y Captura ULTRA (bib)")
        print("  [11] Gestión de Patentes y Freedom to Operate (pat/MOSPAT)")
        print("  [12] Auditoría de Código y Decompilaciones (audit/MOSAUDIT)")
        print("  [13] Configurar ajustes GLOBALES y Supervisor Humano")
        print("  [14] ⚡ Sincronización SOBERANA Git (Commit & Push Forzado)")
        print("  [0] Salir")
        print("-------------------------------------------------------")
        choice = input("Selecciona una opción [0-14]: ").strip()

        if choice == "1":
            selected = select_active_project(pm)
            if selected:
                active_project = selected
        elif choice == "2":
            new_id = menu_create_project(pm)
            if new_id:
                active_project = new_id
        elif choice == "3":
            menu_configure_project(pm, active_project=active_project)
        elif choice == "4":
            menu_view_project_details(pm, active_project=active_project)
        elif choice == "5":
            menu_create_item(pm, active_project=active_project)
        elif choice == "6":
            menu_edit_item(pm, active_project=active_project)
        elif choice == "7":
            menu_compile_project(pm, active_project=active_project)
        elif choice == "8":
            menu_compile_all_projects(pm)
        elif choice == "9":
            menu_review_agent_proposal(pm, active_project=active_project)
        elif choice == "10":
            menu_bib_management(data_dir, pm)
        elif choice == "11":
            menu_patent_management(data_dir, pm)
        elif choice == "12":
            menu_audit_management(data_dir, pm)
        elif choice == "13":
            menu_configure_global_settings(data_dir)
        elif choice == "14":
            menu_git_sovereign_sync()
        elif choice == "0":
            print("\n👋 Saliendo de MOM. ¡Soberanía y control garantizados!")
            break


def main() -> None:
    projects_dir = current_dir.parent / "data" / "projects"
    data_dir = current_dir.parent / "data"
    
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
        pm = ProjectManager(projects_root=projects_dir)
        
        if args.command == "projects":
            if args.action == "list":
                for p in pm.projects_root.iterdir():
                    if p.is_dir() and (p / "project.json").exists():
                        print(f"  - {p.name}")
            elif args.action == "create":
                parents = [p.strip() for p in args.parents.split(",")] if args.parents else []
                pm.create_project(name=args.name, parents=parents)
        elif args.command == "compile":
            repo = MOMInheritedRepository(pm.projects_root, args.project)
            compiler = MOMCompiler(repo)
            if not compiler.validate_graph():
                compiler.compile_all()
    else:
        interactive_main()


if __name__ == "__main__":
    main()

# App Version: 0.6.0
# Script Version: 0.6.0.0
# Schema_Version: 0.5.3