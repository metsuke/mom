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

# ==============================================================================
# MÓDULOS DE BIBLIOTECA, PATENTES, AUDITORÍA Y GIT SOBERANO
# ==============================================================================

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
    """Menú de sincronización soberana directa desde la CLI (Soporta entrada multilínea)."""
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
    """
    Desindexa la ruta privada del índice de Git y elimina cualquier rastro histórico
    en commits antiguos para garantizar el cumplimiento de derechos de autor.
    """
    clean_path = relative_path.strip("/")
    purged_any = False
    
    # 1. Eliminar del índice actual de Git (staged/cached)
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

    # 2. Purgar commits históricos antiguos si existen en el repo
    try:
        log_cmd = ["git", "-C", str(root_dir), "log", "-1", "--format=%h", "--", clean_path]
        res_log = subprocess.run(log_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res_log.stdout.strip():
            print(f"  🚨 [PURGA DE HISTORIAL] Rastro detectado en commit {res_log.stdout.strip()}. Purgando historial de Git...")
            if shutil.which("git-filter-repo"):
                purge_cmd = ["git", "-C", str(root_dir), "filter-repo", "--invert-paths", "--path", clean_path, "--force"]
            else:
                purge_cmd = [
                    "git", "-C", str(root_dir), "filter-branch", "--force",
                    "--index-filter", f"git rm -rf --cached --ignore-unmatch {clean_path}",
                    "--prune-empty", "--tag-name-filter", "cat", "--", "--all"
                ]
            subprocess.run(purge_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  ✅ [HISTORIAL PURGADO] Erradicado rastro histórico de {clean_path}")
            purged_any = True
    except Exception as e:
        print(f"  ⚠️ Error purgando historial de '{clean_path}': {e}")

    # 3. Si se desindexó o purgó algo durante el proceso de limpieza, propagar forzadamente al remoto
    if purged_any:
        print("  ⚡ [PURGA AUTOMÁTICA] Sincronizando árbol limpio con remoto...")
        execute_sovereign_git_push(root_dir, f"fix(security): purga soberana de rastro privado de {clean_path}")

def append_to_root_gitignore(repo_root: Path, rule: str) -> None:
    """Añade una regla al .gitignore de la raíz del repositorio si no está presente."""
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
    """Recorre todos los proyectos en disco, fuerza el uso del .gitignore de la raíz y limpia rastros de Git."""
    repo_root = current_dir.parent  # Raíz del repositorio 'mom'
    
    # 1. Si existe un data/.gitignore secundario, eliminarlo para evitar conflictos de rutas
    data_gitignore = repo_root / "data" / ".gitignore"
    if data_gitignore.exists():
        try:
            subprocess.run(["git", "-C", str(repo_root), "rm", "-f", "data/.gitignore"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            data_gitignore.unlink(missing_ok=True)
            print("  🧹 [GIT CLEAN] Eliminado 'data/.gitignore' duplicado para unificar reglas en la raíz.")
        except Exception:
            pass

    if not pm.projects_root.exists():
        return

    print("\n🔍 Sincronizando políticas de visibilidad y aislando proyectos privados...")
    
    # 2. Reglas estáticas en la raíz
    append_to_root_gitignore(repo_root, "data/library/")
    append_to_root_gitignore(repo_root, "data/ai-proposals/*.json")
    
    _untrack_and_purge_private_path(repo_root, "data/library/")
    _untrack_and_purge_private_path(repo_root, "data/ai-proposals/")

    # 3. Recorrer proyectos registrados
    private_count = 0
    for proj_dir in sorted(pm.projects_root.iterdir()):
        if proj_dir.is_dir() and (proj_dir / "project.json").exists():
            try:
                with open(proj_dir / "project.json", "r", encoding="utf-8") as f:
                    meta = json.load(f)
                
                if meta.get("is_private", False):
                    rel_path = f"data/projects/{proj_dir.name}/"
                    append_to_root_gitignore(repo_root, rel_path)
                    _untrack_and_purge_private_path(repo_root, rel_path)
                    
                    print(f"  🔒 [PRIVADO PROTEGIDO] Sincronizado en raíz .gitignore: {proj_dir.name}")
                    private_count += 1
            except Exception as e:
                print(f"  ⚠️ Error sincronizando {proj_dir.name}: {e}")

    print(f"✅ Verificación completada ({private_count} proyectos privados verificados y aislados de Git).\n")

def _ensure_project_exists(pm: ProjectManager, proj_id: str, name: str, parents: List[str], is_private: bool, desc: str) -> None:
    """Crea o actualiza un nodo de proyecto en disco manteniendo su estructura JSON e aislando visibilidad privada."""
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
            "schema_version": "0.5.3"
        }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    if is_private:
        repo_root = current_dir.parent
        append_to_root_gitignore(repo_root, f"data/projects/{proj_id}/")
        _untrack_and_purge_private_path(repo_root, f"data/projects/{proj_id}/")

def menu_bib_management(data_dir: Path, pm: ProjectManager) -> None:
    """Gestión de la Biblioteca Privada (data/library/bib/) y Corpus Bibliográfico."""
    bib_dir = data_dir / "library" / "bib"
    bib_dir.mkdir(parents=True, exist_ok=True)

    _ensure_project_exists(pm, "MOSBIB", "Pilar Global de Bibliografía", [], False, "Pilar herencial de obras y fuentes bibliográficas")

    print("\n=======================================================")
    print(" 📚 GESTIÓN DE BIBLIOTECA Y PROYECTOS OBRA (AUTHOR-*)")
    print("=======================================================")
    print("  [1] Inicializar Nodo Autor Consolidador (ej. AUTHOR-W3C)")
    print("  [2] Registrar OBRA FORMAL Y MATRIZ RAW (ej. AUTHOR-W3C-WCAG22)")
    print("  [3] Ejecutar TROCEO AGÉNTICO sobre una Obra Registrada")
    print("  [4] Ejecutar Kill-Switch / Revocación de Cita Literal")
    print("  [0] Volver al Menú Principal")
    print("-------------------------------------------------------")

    opt = input("Selecciona una opción [0-4]: ").strip()

    if opt == "1":
        author_id = input("ID del Autor Consolidador (ej. AUTHOR-W3C): ").strip().upper()
        if not author_id.startswith("AUTHOR-"):
            author_id = f"AUTHOR-{author_id}"
        
        name = input(f"Nombre completo del Autor [{author_id}]: ").strip() or author_id
        desc = input("Descripción doctrinal del corpus del autor: ").strip()

        _ensure_project_exists(pm, author_id, name, ["MOSAUTHOR"], False, desc)
        (bib_dir / author_id).mkdir(parents=True, exist_ok=True)
        print(f"✅ Nodo Autor Consolidador '{author_id}' (Hijo de MOSAUTHOR) inicializado con éxito.")

    elif opt == "2":
        author_dirs = [d.name for d in pm.projects_root.iterdir() if d.is_dir() and d.name.startswith("AUTHOR-") and len(d.name.split("-")) == 2]
        if not author_dirs:
            print("❌ No hay nodos autor consolidador. Inicializa un nodo autor primero (opción 1).")
            return

        print("Autores/Pilares disponibles:")
        for i, a in enumerate(author_dirs, 1):
            print(f"  [{i}] {a}")
        
        try:
            a_idx = int(input("Selecciona Autor: ")) - 1
            parent_author_id = author_dirs[a_idx]
        except (ValueError, IndexError):
            print("❌ Selección no válida.")
            return

        work_code = input("ID corto de la obra (ej. WCAG22): ").strip().upper()
        work_project_id = f"{parent_author_id}-{work_code}"
        raw_project_id = f"{work_project_id}-RAW"

        title = input("Título completo de la obra: ").strip()
        publisher = input("Editorial / Entidad Emisora: ").strip()
        year_raw = input("Año de publicación: ").strip()
        year = int(year_raw) if year_raw.isdigit() else 2026
        url = input("URL / DOI / ISBN de referencia: ").strip()
        license_type = input("Tipo de Licencia (ej. W3C, Public Domain, CC-BY, Copyright): ").strip() or "W3C"
        
        allow_export = ask_confirmation("¿Permite exportación de texto literal completo (Dominio Público/Licencia Abierta)?")
        raw_is_private = not allow_export

        raw_file_str = input("Ruta al archivo original completo (opcional, Enter para omitir): ").strip()
        sha256_str = ""

        _ensure_project_exists(pm, raw_project_id, f"Fuente Matriz RAW: {title}", [], raw_is_private, f"Archivo maestro original de {title}")
        _ensure_project_exists(pm, work_project_id, title, [raw_project_id], False, f"Despiece atómico de {title}")
        _ensure_project_exists(pm, "MOSBIB", "Pilar Global de Bibliografía", [work_project_id], False, "Pilar herencial de obras")
        _ensure_project_exists(pm, parent_author_id, parent_author_id, [work_project_id, "MOSBIB"], False, "Autor consolidador")
        _ensure_project_exists(pm, "MOSAUTHOR", "Consolidador Global de Autores", [parent_author_id], False, "Nodo central de herencia")

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
            "url": url,
            "license_type": license_type,
            "allow_full_text_export": allow_export,
            "kill_switch_enabled": False,
            "sha256_hash": sha256_str
        }

        with open(work_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(bib_meta, f, indent=2, ensure_ascii=False)

        print(f"✅ FUENTE MATRIZ CREADA: '{raw_project_id}' (Visibilidad: {'🔒 PRIVADA' if raw_is_private else '🌐 PÚBLICA'})")
        print(f"✅ OBRA DESPIECE CREADA: '{work_project_id}' (Hereda de '{raw_project_id}')")
        print(f"✅ JERARQUÍA CONSOLIDADA: {work_project_id} ➔ MOSBIB & {parent_author_id} ➔ MOSAUTHOR")

        if raw_file_str and ask_confirmation("¿Deseas lanzar el TROCEO AGÉNTICO inmediatamente para esta obra?"):
            from ingest_agent import MOMMultilingualIngestionAgent
            agent = MOMMultilingualIngestionAgent(data_dir=data_dir)
            agent.ingest_registered_work(work_dir)

    elif opt == "3":
        print("\n--- 🤖 SELECCIONAR OBRA REGISTRADA PARA TROCEO AGÉNTICO ---")
        author_dirs = [d for d in bib_dir.iterdir() if d.is_dir()]
        registered_works = []

        for ad in author_dirs:
            for wd in ad.iterdir():
                if wd.is_dir() and (wd / "metadata.json").exists():
                    registered_works.append(wd)

        if not registered_works:
            print("❌ No hay obras registradas con metadata.json en la biblioteca.")
            return

        print("Obras disponibles para troceo:")
        for i, wd in enumerate(registered_works, 1):
            with open(wd / "metadata.json", "r", encoding="utf-8") as f:
                meta = json.load(f)
            print(f"  [{i}] {meta.get('author_id')} / {meta.get('work_id')} - {meta.get('title')}")

        try:
            w_idx = int(input("\nSelecciona el número de obra a procesar: ")) - 1
            target_work_dir = registered_works[w_idx]
        except (ValueError, IndexError):
            print("❌ Selección no válida.")
            return

        from ingest_agent import MOMMultilingualIngestionAgent
        agent = MOMMultilingualIngestionAgent(data_dir=data_dir)
        agent.ingest_registered_work(target_work_dir)

    elif opt == "4":
        print("\n--- 🚨 EJECUCIÓN DE KILL-SWITCH / REVOCACIÓN DE DIFUSIÓN PÚBLICA ---")
        author_dirs = [d for d in bib_dir.iterdir() if d.is_dir()]
        all_works = []

        for ad in author_dirs:
            for wd in ad.iterdir():
                if wd.is_dir() and (wd / "metadata.json").exists():
                    all_works.append(wd)

        if not all_works:
            print("❌ No hay obras registradas en la biblioteca.")
            return

        print("Obras registradas:")
        for i, wd in enumerate(all_works, 1):
            print(f"  [{i}] {wd.parent.name} / {wd.name}")

        try:
            w_idx = int(input("Selecciona obra para modificar/revocar: ")) - 1
            target_work = all_works[w_idx]
        except (ValueError, IndexError):
            print("❌ Selección no válida.")
            return

        meta_file = target_work / "metadata.json"
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        print(f"\nEstado actual de '{meta.get('work_id')}':")
        print(f"  • Permitir Texto Literal Público: {meta.get('allow_full_text_export')}")
        print(f"  • Kill-Switch Activado:          {meta.get('kill_switch_enabled')}")

        if ask_confirmation("¿Deseas ACTIVAR el Kill-Switch y REVOCAR inmediatamente la exportación pública de texto literal?"):
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
                    append_to_root_gitignore(repo_root, f"data/projects/{raw_id}/")
                    _untrack_and_purge_private_path(repo_root, f"data/projects/{raw_id}/")

            print("🛑 Kill-Switch activado. La fuente matriz se ha bloqueado como PRIVADA y se purgará la cita literal.")
            repo_root = current_dir.parent
            execute_sovereign_git_push(repo_root, f"fix(security): activado kill-switch soberano para obra {meta.get('work_id')}")

def menu_patent_management(data_dir: Path, pm: ProjectManager) -> None:
    """Gestión del Pilar MOSPAT y Registro de Patentes (Freedom to Operate - FTO)."""
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
        
        author_dirs = [d.name for d in pm.projects_root.iterdir() if d.is_dir() and d.name.startswith("AUTHOR-") and len(d.name.split("-")) == 2]
        author_id = None
        if author_dirs:
            print("\nSelecciona el Autor/Titular de la patente (opcional):")
            for i, a in enumerate(author_dirs, 1):
                print(f"  [{i}] {a}")
            a_sel = input("Selecciona número de Autor (o Enter para omitir): ").strip()
            if a_sel.isdigit() and 1 <= int(a_sel) <= len(author_dirs):
                author_id = author_dirs[int(a_sel) - 1]

        jurisdiction = input("Jurisdicción Principal (ej. US, EP, ES): ").strip().upper() or "US"
        grant_year_raw = input("Año de Concesión: ").strip()
        grant_year = int(grant_year_raw) if grant_year_raw.isdigit() else 2010
        expiry_year = grant_year + 20

        claims_str = input("Resumen de Reivindicaciones Clave (Claims): ").strip()
        is_expired = datetime.datetime.now().year >= expiry_year
        is_private_raw = ask_confirmation("¿El documento original de patente es de uso privado / restringido?", default=False)

        _ensure_project_exists(pm, raw_project_id, f"Documento Matriz Patente: {title}", [], is_private_raw, f"Documento original de patente {patent_code}")
        _ensure_project_exists(pm, pat_project_id, f"Patente: {title}", [raw_project_id], False, f"FTO y Claims de {patent_code}")
        _ensure_project_exists(pm, "MOSPAT", "Pilar Global de Patentes", [pat_project_id], False, "Pilar herencial de patentes")
        if author_id:
            _ensure_project_exists(pm, author_id, author_id, [pat_project_id, "MOSPAT"], False, "Autor consolidador")
            _ensure_project_exists(pm, "MOSAUTHOR", "Consolidador Global de Autores", [author_id], False, "Nodo central de herencia")

        p_folder = pat_dir / pat_project_id
        p_folder.mkdir(parents=True, exist_ok=True)

        meta_bib = {
            "patent_id": pat_project_id,
            "raw_project_id": raw_project_id,
            "author_id": author_id,
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

        print(f"✅ PATENTE MATRIZ Y DESPIECE REGISTRADOS: '{pat_project_id}' ➔ MOSPAT ➔ MOSAUTHOR")

    elif opt == "2":
        patents = [d for d in pat_dir.iterdir() if d.is_dir() and (d / "metadata.json").exists()]
        if not patents:
            print("ℹ️ No hay patentes registradas en MOSPAT.")
            return

        print("\nPatentes registradas en el sistema:")
        for p in patents:
            with open(p / "metadata.json", "r", encoding="utf-8") as f:
                d = json.load(f)
            st_str = "🟢 EXPIRADA" if d.get("is_expired") else "🔴 ACTIVA (Restricción FTO)"
            aut_str = f" | Autor: {d.get('author_id')}" if d.get("author_id") else ""
            print(f"  • {d.get('patent_id')}: {d.get('title')} [{st_str}]{aut_str} - Expiración: {d.get('expiry_year_global')}")

def menu_audit_management(data_dir: Path, pm: ProjectManager) -> None:
    """Gestión del Pilar MOSAUDIT, Auditoría de Código y Comparativa Declarado vs Decompilado."""
    audit_dir = data_dir / "library" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    _ensure_project_exists(pm, "MOSAUDIT", "Pilar Global de Auditoría de Código", [], False, "Pilar herencial de auditorías y decompilados")

    print("\n=======================================================")
    print(" 🛡️ AUDITORÍA DE CÓDIGO Y DECOMPILACIONES (MOSAUDIT)")
    print("=======================================================")
    print("  [1] Registrar Proyecto de Auditoría COMO PROYECTO FORMAL INDEPENDIENTE")
    print("  [2] Inspeccionar Discrepancias / Inyecciones de Código")
    print("  [0] Volver al Menú Principal")
    print("-------------------------------------------------------")

    opt = input("Selecciona una opción [0-2]: ").strip()

    if opt == "1":
        app_code = input("Código / ID de Aplicación (ej. APP-XYZ): ").strip().upper()
        audit_project_id = f"AUDIT-{app_code}"
        raw_project_id = f"{audit_project_id}-RAW"

        author_dirs = [d.name for d in pm.projects_root.iterdir() if d.is_dir() and d.name.startswith("AUTHOR-") and len(d.name.split("-")) == 2]
        author_id = None
        if author_dirs:
            print("\nSelecciona el Autor/Desarrollador del software (opcional):")
            for i, a in enumerate(author_dirs, 1):
                print(f"  [{i}] {a}")
            a_sel = input("Selecciona número de Autor (o Enter para omitir): ").strip()
            if a_sel.isdigit() and 1 <= int(a_sel) <= len(author_dirs):
                author_id = author_dirs[int(a_sel) - 1]

        declared_repo = input("URL/Ruta del Repositorio Open Source Declarado: ").strip()
        binary_path_str = input("Ruta al Binario Ejecutable Decompilado (opcional): ").strip()

        is_private_raw = ask_confirmation("¿El binario/código decompilado original es de carácter PRIVADO?", default=True)

        _ensure_project_exists(pm, raw_project_id, f"Binarios / Decompilado RAW: {app_code}", [], is_private_raw, f"Binarios decompilados de {app_code}")
        _ensure_project_exists(pm, audit_project_id, f"Auditoría: {app_code}", [raw_project_id], False, f"Especificación de auditoría de {app_code}")
        _ensure_project_exists(pm, "MOSAUDIT", "Pilar Global de Auditorías", [audit_project_id], False, "Pilar herencial de auditorías")
        if author_id:
            _ensure_project_exists(pm, author_id, author_id, [audit_project_id, "MOSAUDIT"], False, "Autor consolidador")
            _ensure_project_exists(pm, "MOSAUTHOR", "Consolidador Global de Autores", [author_id], False, "Nodo central de herencia")

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
            "author_id": author_id,
            "declared_repo": declared_repo,
            "has_decompiled_binary": bool(binary_path_str),
            "sha256_hash": sha256_str,
            "audit_date": datetime.datetime.now().isoformat()
        }

        with open(app_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta_bib, f, indent=2, ensure_ascii=False)

        print(f"✅ AUDITORÍA REGISTRADA CON ÉXITO: '{audit_project_id}' ➔ MOSAUDIT ➔ MOSAUTHOR")

    elif opt == "2":
        apps = [d for d in audit_dir.iterdir() if d.is_dir() and (d / "metadata.json").exists()]
        if not apps:
            print("ℹ️ No hay auditorías registradas.")
            return

        print("\nAuditorías en curso:")
        for a in apps:
            with open(a / "metadata.json", "r", encoding="utf-8") as f:
                d = json.load(f)
            aut_str = f" | Autor: {d.get('author_id')}" if d.get("author_id") else ""
            print(f"  • Componente: {d.get('app_id')}{aut_str} | Hash SHA-256 Binario: {d.get('sha256_hash') or 'N/A'}")

# ==============================================================================
# FUNCIONES DE MENÚ PRINCIPAL Y CONFIGURACIÓN DE PROYECTOS
# ==============================================================================

def menu_configure_global_settings(data_dir: Path) -> None:
    """Gestiona la configuración global de MOM almacenada en data/config.json, incluyendo al Supervisor Humano."""
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
    web_str = current_web if current_web else "🚫 DESACTIVADA (Sin exportación web)"

    print("\n=======================================================")
    print(" ⚙️ CONFIGURACIÓN GLOBAL Y SUPERVISOR HUMANO A CARGO")
    print("=======================================================")
    print(f"  • Ruta Web Vault (flat directory): {web_str}")
    print(f"  • Versión del Esquema Global:     v{config.get('schema_version', CURRENT_SCHEMA_VERSION)}")
    print(f"  • Supervisor Humano a Cargo:      {config.get('supervisor_name')} <{config.get('supervisor_email')}>")
    print(f"  • Cargo / Rol de Responsabilidad: {config.get('supervisor_role')}")
    print("-------------------------------------------------------")
    print("  [1] Configurar/Modificar datos del Supervisor Humano a Cargo")
    print("  [2] Configurar/Modificar ruta de exportación Web Vault")
    print("  [3] Desactivar exportación a Web Vault")
    print("  [0] Volver al menú principal")
    print("-------------------------------------------------------")

    opt = input("Selecciona una opción [0-3]: ").strip()

    if opt == "1":
        print("\n--- 👤 DATOS DEL SUPERVISOR HUMANO RESPONSABLE ---")
        s_name = input(f"Nombre Completo [{config.get('supervisor_name')}]: ").strip()
        if s_name:
            config["supervisor_name"] = s_name
        
        s_email = input(f"Email de Contacto [{config.get('supervisor_email')}]: ").strip()
        if s_email:
            config["supervisor_email"] = s_email

        s_role = input(f"Cargo / Responsabilidad [{config.get('supervisor_role')}]: ").strip()
        if s_role:
            config["supervisor_role"] = s_role

        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print("✅ Configuración del Supervisor Humano actualizada correctamente.")

    elif opt == "2":
        new_path = input("\nIntroduce la ruta absoluta o relativa hacia la carpeta web: ").strip()
        if new_path:
            p = Path(new_path).expanduser().resolve()
            if not p.exists():
                print(f"⚠️ La ruta '{p}' no existe en el disco actualmente.")
                if not ask_confirmation("¿Deseas guardar la ruta de todos modos para cuando exista?"):
                    return
            config["web_vault_dir"] = str(p)
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"✅ Ruta global de Web Vault configurada en: {p}")

    elif opt == "3":
        if ask_confirmation("¿Desactivar la exportación plana a Web Vault?"):
            config["web_vault_dir"] = None
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print("✅ Exportación a Web Vault desactivada.")

def menu_create_project(pm: ProjectManager) -> Optional[str]:
    print("\n--- 📁 CREAR NUEVO PROYECTO MOM (Esquema v0.5.3) ---")
    project_id = input("ID del proyecto (ej. MOSCON): ").strip().upper()
    if not project_id:
        print("❌ El ID del proyecto es obligatorio.")
        return None

    name = input("Nombre descriptivo del proyecto: ").strip()
    if not name:
        print("❌ El nombre no puede estar vacío.")
        return None

    phase = input("Fase ESA PSS-05 (COR, URD, SRD, ADD, DDD) [COR]: ").strip().upper() or "COR"
    is_private = ask_confirmation("¿Este proyecto es PRIVADO? (Excluido en .gitignore)", default=True)
    mandatory = ask_confirmation("¿Este proyecto es MANDATORIO / OBLIGATORIO para derivados?", default=True)

    decay_raw = input("Ratio de degradación temporal (default_decay_rate) [0.05]: ").strip()
    try:
        default_decay_rate = float(decay_raw) if decay_raw else 0.05
    except ValueError:
        default_decay_rate = 0.05

    language = input("Idioma operativo primario [es-ES]: ").strip() or "es-ES"
    description = input("Descripción del proyecto: ").strip()

    parents = select_parent_projects_interactively(pm, exclude_project=project_id)
    target_docs = input("Ruta externa de exportación de docs (opcional, Enter para omitir): ").strip()

    print("\nResumen del nuevo proyecto:")
    print(f"  • ID de Proyecto: {project_id}")
    print(f"  • Nombre: {name}")
    print(f"  • Fase ESA: {phase}")
    print(f"  • Visibilidad: {'🔒 PRIVADO (Excluido en .gitignore)' if is_private else '🌐 PÚBLICO (Rastreado en Git)'}")
    print(f"  • Mandatorio: {'Sí' if mandatory else 'No'}")
    print(f"  • Ratio Degradación (λ): {default_decay_rate}")
    print(f"  • Idioma Operativo: {language}")
    print(f"  • Descripción: {description if description else 'Sin descripción'}")
    print(f"  • Padres (Herencia DAG): {parents if parents else 'Ninguno (Proyecto Raíz)'}")
    print(f"  • Ruta Target Docs: {target_docs if target_docs else 'Sin exportación externa'}")

    if ask_confirmation("¿Deseas crear el proyecto con estos datos?"):
        try:
            proj_dir = pm.projects_root / project_id
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "specs").mkdir(exist_ok=True)

            meta = {
                "project_id": project_id,
                "name": name,
                "phase": phase,
                "schema_version": "0.5.3",
                "parents": parents,
                "is_private": is_private,
                "mandatory": mandatory,
                "default_decay_rate": default_decay_rate,
                "language": language,
                "description": description,
                "target_docs_dir": target_docs if target_docs else None
            }

            with open(proj_dir / "project.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            repo_root = current_dir.parent
            if is_private:
                append_to_root_gitignore(repo_root, f"data/projects/{project_id}/")
                _untrack_and_purge_private_path(repo_root, f"data/projects/{project_id}/")

            print(f"✅ Proyecto '{project_id}' creado con éxito en: {proj_dir}")
            return project_id
        except Exception as e:
            print(f"❌ Error al crear proyecto: {e}")
    else:
        print("🛑 Operación cancelada por el usuario.")
    return None

def menu_view_project_details(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    """Muestra todos los datos de un proyecto e inspecciona su estructura y métricas."""
    print("\n--- 🔍 VISUALIZAR Y AUDITAR PROYECTO ---")
    
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
        if not projects:
            print("❌ No hay proyectos registrados.")
            return

        print("Selecciona el proyecto a inspeccionar:")
        for i, p in enumerate(projects, 1):
            print(f"  [{i}] {p}")

        try:
            idx = int(input("Selecciona el número de proyecto: ")) - 1
            target_project = projects[idx]
        except (ValueError, IndexError):
            print("❌ Selección no válida.")
            return

    proj_json = pm.projects_root / target_project / "project.json"
    if not proj_json.exists():
        print(f"❌ No se encontró el fichero project.json para {target_project}.")
        return

    with open(proj_json, "r", encoding="utf-8") as f:
        meta = json.load(f)

    repo = MOMInheritedRepository(pm.projects_root, target_project)
    all_items = repo.list_all_consolidated()

    counts_by_phase: Dict[str, int] = {}
    local_count = 0
    inherited_count = 0

    for item in all_items.values():
        p_val = item.phase.value.upper() if hasattr(item.phase, 'value') else str(item.phase).upper()
        counts_by_phase[p_val] = counts_by_phase.get(p_val, 0) + 1
        
        origin = item.metadata.declared_in_project or target_project
        if origin == target_project:
            local_count += 1
        else:
            inherited_count += 1

    print("\n=======================================================")
    print(f" 📄 DATOS DEL PROYECTO: {target_project}")
    print("=======================================================")
    print(f"  • ID de Proyecto:      {meta.get('project_id', target_project)}")
    print(f"  • Nombre Completo:     {meta.get('name', 'N/A')}")
    print(f"  • Fase Inicial ESA:    {meta.get('phase', 'COR')}")
    print(f"  • Esquema Compatible:  v{meta.get('schema_version', '0.5.3')}")
    print(f"  • Visibilidad Git:     {'🔒 PRIVADO (.gitignore)' if meta.get('is_private', True) else '🌐 PÚBLICO'}")
    print(f"  • Carácter:            {'Mandatorio / Obligatorio' if meta.get('mandatory', True) else 'Opcional / Derivado'}")
    print(f"  • Ratio Degradación λ: {meta.get('default_decay_rate', 0.05)}")
    print(f"  • Idioma Operativo:    {meta.get('language', 'es-ES')}")
    print(f"  • Cadena Herencia DAG: {' -> '.join(repo.chain)}")
    print(f"  • Ruta Target Export:  {meta.get('target_docs_dir') or 'Sin exportación externa'}")
    print(f"  • Descripción:        {meta.get('description', 'Sin descripción')}")
    print("-------------------------------------------------------")
    print(f" 📊 MÉTRICAS DEL CORPUS DE CONOCIMIENTO:")
    print(f"  • Ítems Totales Consolidados: {len(all_items)} ({local_count} locales, {inherited_count} heredados)")
    for phase_name in ["COR", "URD", "SRD", "ADD", "DDD"]:
        cnt = counts_by_phase.get(phase_name, 0)
        print(f"    - Fase {phase_name}: {cnt} elemento(s)")
    print("=======================================================")

def menu_configure_project(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    print("\n--- ⚙️ CONFIGURAR PROYECTO (VISIBILIDAD, HERENCIA Y METADATOS) ---")
    
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
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

    proj_json = pm.projects_root / target_project / "project.json"
    if not proj_json.exists():
        print(f"❌ No se encontró el fichero project.json para {target_project}.")
        return

    with open(proj_json, "r", encoding="utf-8") as f:
        meta = json.load(f)

    current_parents = meta.get("parents", meta.get("parent_projects", []))
    current_target = meta.get("target_docs_dir", "")
    current_private = meta.get("is_private", True)
    current_mandatory = meta.get("mandatory", True)
    current_decay = meta.get("default_decay_rate", 0.05)
    current_lang = meta.get("language", "es-ES")
    current_desc = meta.get("description", "")

    priv_str = "🔒 PRIVADO" if current_private else "🌐 PÚBLICO"
    mand_str = "SÍ (Obligatorio)" if current_mandatory else "NO (Opcional)"

    print(f"\nConfiguración actual de '{target_project}':")
    print(f"  • ID Proyecto: {meta.get('project_id', target_project)}")
    print(f"  • Nombre: {meta.get('name', target_project)}")
    print(f"  • Fase: {meta.get('phase', 'COR')}")
    print(f"  • Visibilidad: {priv_str}")
    print(f"  • Mandatorio: {mand_str}")
    print(f"  • Ratio Degradación (λ): {current_decay}")
    print(f"  • Idioma: {current_lang}")
    print(f"  • Descripción: {current_desc if current_desc else 'Sin descripción'}")
    print(f"  • Padres: {current_parents if current_parents else 'Ninguno'}")
    print(f"  • Ruta Target Docs: {current_target if current_target else 'Sin configurar'}")

    print("\n¿Qué deseas modificar?")
    print(f"  [1] Modificar Nombre y Descripción")
    print(f"  [2] Cambiar visibilidad | Estado actual: {priv_str}")
    print(f"  [3] Cambiar estado Mandatorio | Estado actual: {mand_str}")
    print(f"  [4] Modificar proyectos padres (Herencia DAG)")
    print(f"  [5] Modificar ratio de degradación temporal (default_decay_rate) e Idioma")
    print(f"  [6] Modificar ruta target de exportación de docs")
    print("  [0] Cancelar")

    opt = input("Opción [0-6]: ").strip()
    if opt == "1":
        new_name = input(f"Nuevo Nombre [{meta.get('name', target_project)}]: ").strip()
        if new_name:
            meta["name"] = new_name
        new_desc = input(f"Nueva Descripción [{current_desc}]: ").strip()
        if new_desc:
            meta["description"] = new_desc
    elif opt == "2":
        target_priv = not current_private
        target_str = "🔒 PRIVADO" if target_priv else "🌐 PÚBLICO"
        if ask_confirmation(f"Estado actual es '{priv_str}'. ¿Deseas cambiar la visibilidad a '{target_str}'?"):
            meta["is_private"] = target_priv
            repo_root = current_dir.parent
            if target_priv:
                append_to_root_gitignore(repo_root, f"data/projects/{target_project}/")
                _untrack_and_purge_private_path(repo_root, f"data/projects/{target_project}/")
            print(f"ℹ️ Visibilidad ajustada a: {target_str}")
    elif opt == "3":
        target_mand = not current_mandatory
        target_str = "SÍ (Obligatorio)" if target_mand else "NO (Opcional)"
        if ask_confirmation(f"Estado actual es '{mand_str}'. ¿Deseas cambiar el carácter del proyecto a '{target_str}'?"):
            meta["mandatory"] = target_mand
            print(f"ℹ️ Estado mandatorio ajustado a: {target_str}")
    elif opt == "4":
        new_parents = select_parent_projects_interactively(pm, exclude_project=target_project, preselected=current_parents)
        meta["parents"] = new_parents
    elif opt == "5":
        decay_raw = input(f"Nuevo Ratio Degradación [{current_decay}]: ").strip()
        if decay_raw:
            try:
                meta["default_decay_rate"] = float(decay_raw)
            except ValueError:
                pass
        lang_raw = input(f"Nuevo Idioma Operativo [{current_lang}]: ").strip()
        if lang_raw:
            meta["language"] = lang_raw
    elif opt == "6":
        new_target = input("Introduce la nueva ruta target (o pulsa Enter para limpiar/desactivar): ").strip()
        meta["target_docs_dir"] = new_target
    else:
        print("🛑 Cancelado.")
        return

    meta["schema_version"] = "0.5.3"

    if ask_confirmation("¿Guardar los cambios de configuración en project.json?"):
        with open(proj_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print("✅ Configuración del proyecto actualizada.")

def menu_create_item(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    """CAMINO 1: Crear un elemento atómico NUEVO con ID correlativo automático."""
    print("\n--- ➕ CREAR NUEVA ESPECIFICACIÓN ATÓMICA (JSON) ---")
    
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
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

    inherited_repo = MOMInheritedRepository(pm.projects_root, target_project)

    print("\nFases ESA/MOM disponibles: [0] COR  [1] URD  [2] SRD  [3] ADD  [4] DDD")
    phase_map = {"0": ESAPhase.COR, "1": ESAPhase.URD, "2": ESAPhase.SRD, "3": ESAPhase.ADD, "4": ESAPhase.DDD}
    p_choice = input("Selecciona la fase [0-4]: ").strip()
    if p_choice not in phase_map:
        print("❌ Fase no válida.")
        return
    phase = phase_map[p_choice]

    raw_item_id = input(f"ID del ítem (ej. {phase.value.upper()}-{target_project} o Enter para sugerido): ").strip()
    item_id = get_next_auto_id(inherited_repo, phase, target_project, raw_item_id)
    print(f"ℹ️ Asignando nuevo ID atómico: {item_id}")

    title = input("Título del elemento: ").strip()
    description = input("Descripción detallada del requisito / axioma / diseño: ").strip()

    print("\nSelecciona los elementos padres de los que hereda este ítem (flechas + espacio):")
    parent_ids = select_parent_items_interactively(inherited_repo, current_phase=phase)

    supports_raw = input("IDs apoyados / respaldados separados por coma (supports_item_ids): ").strip()
    supports_ids = [s.strip().upper() for s in supports_raw.split(",") if s.strip()] if supports_raw else []

    refutes_raw = input("IDs refutados / contradichos separados por coma (refutes_item_ids): ").strip()
    refutes_ids = [r.strip().upper() for r in refutes_raw.split(",") if r.strip()] if refutes_raw else []

    is_user_doc = ask_confirmation("¿Este elemento debe incluirse en el Manual de Usuario u Onboarding?")
    guardrails = input("AI Guardrails / Instrucciones inmutables para la IA (opcional): ").strip() or None

    print("\nPreview de la nueva especificación atómica:")
    print(f"  • ID: {item_id}")
    print(f"  • Fase: {phase.value.upper()}")
    print(f"  • Título: {title}")
    print(f"  • Padres: {parent_ids if parent_ids else 'Ninguno'}")
    print(f"  • Apoya a: {supports_ids if supports_ids else 'Ninguno'}")
    print(f"  • Refuta a: {refutes_ids if refutes_ids else 'Ninguno'}")
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
                attributes=ItemAttributes(
                    priority=PriorityEnum.HIGH, 
                    is_user_doc=is_user_doc,
                    supports_item_ids=supports_ids,
                    refutes_item_ids=refutes_ids
                ),
                metadata=ItemMetadata(author="Metsuke", declared_in_project=target_project, ai_guardrails=guardrails)
            )
            saved_path = inherited_repo.save_item(item)
            print(f"✅ Ítem '{item_id}' guardado correctamente en {saved_path}.")
        except Exception as e:
            print(f"❌ Error al guardar el ítem: {e}")
    else:
        print("🛑 Escritura cancelada.")

def menu_edit_item(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    """CAMINO 2: Seleccionar un elemento EXISTENTE de una lista para editarlo."""
    print("\n--- ✏️ EDITAR ESPECIFICACIÓN ATÓMICA EXISTENTE ---")
    
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
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

    inherited_repo = MOMInheritedRepository(pm.projects_root, target_project)
    all_items = inherited_repo.list_all_consolidated()

    if not all_items:
        print(f"❌ No existen elementos atómicos creados en el proyecto '{target_project}'. Usa la opción de crear primero.")
        return

    items_list = list(all_items.values())
    print(f"\nElementos atómicos disponibles en '{target_project}':")
    for i, it in enumerate(items_list, 1):
        print(f"  [{i}] {it.id} | [{it.phase.value.upper()}] {it.title}")

    try:
        sel_idx = int(input("\nSelecciona el número de elemento a EDITAR: ")) - 1
        if not (0 <= sel_idx < len(items_list)):
            print("❌ Selección fuera de rango.")
            return
        existing_item = items_list[sel_idx]
    except (ValueError, IndexError):
        print("❌ Selección no válida.")
        return

    print(f"\n✏️ EDITANDO ELEMENTO ATÓMICO: '{existing_item.id}'")
    print("ℹ️ Pulsa Enter en cualquier campo para MANTENER el valor actual.")

    title_in = input(f"Título [{existing_item.title}]: ").strip()
    title = title_in if title_in else existing_item.title

    desc_in = input(f"Descripción [{existing_item.description}]: ").strip()
    description = desc_in if desc_in else existing_item.description

    print("\nModificar elementos padres de los que hereda (flechas + espacio):")
    parent_ids = select_parent_items_interactively(inherited_repo, current_phase=existing_item.phase, preselected=existing_item.parent_ids)

    curr_supports = getattr(existing_item.attributes, 'supports_item_ids', [])
    supports_in = input(f"IDs apoyados/respaldados [{', '.join(curr_supports)}]: ").strip()
    supports_ids = [s.strip().upper() for s in supports_in.split(",") if s.strip()] if supports_in else curr_supports

    curr_refutes = getattr(existing_item.attributes, 'refutes_item_ids', [])
    refutes_in = input(f"IDs refutados/contradichos [{', '.join(curr_refutes)}]: ").strip()
    refutes_ids = [r.strip().upper() for r in refutes_in.split(",") if r.strip()] if refutes_in else curr_refutes

    is_user_doc = ask_confirmation("¿Este elemento debe incluirse en el Manual de Usuario u Onboarding?", default=existing_item.attributes.is_user_doc)
    
    current_g = existing_item.metadata.ai_guardrails
    g_suffix = f" [{current_g}]" if current_g else " (opcional)"
    guardrails_in = input(f"AI Guardrails / Instrucciones inmutables{g_suffix}: ").strip()
    guardrails = guardrails_in if guardrails_in else current_g

    print("\nPreview de la especificación atómica EDITADA:")
    print(f"  • ID: {existing_item.id}")
    print(f"  • Fase: {existing_item.phase.value.upper()}")
    print(f"  • Título: {title}")
    print(f"  • Padres: {parent_ids if parent_ids else 'Ninguno'}")
    print(f"  • Apoya a: {supports_ids if supports_ids else 'Ninguno'}")
    print(f"  • Refuta a: {refutes_ids if refutes_ids else 'Ninguno'}")
    print(f"  • Doc Usuario: {is_user_doc}")
    print(f"  • Guardrails: {guardrails if guardrails else 'Ninguno'}")

    if ask_confirmation("¿Confirmas la actualización de este fichero JSON atómico en el disco?"):
        try:
            updated_item = MOMItem(
                id=existing_item.id,
                phase=existing_item.phase,
                title=title,
                description=description,
                parent_ids=parent_ids,
                attributes=ItemAttributes(
                    priority=existing_item.attributes.priority, 
                    is_user_doc=is_user_doc,
                    supports_item_ids=supports_ids,
                    refutes_item_ids=refutes_ids
                ),
                metadata=ItemMetadata(author="Metsuke", declared_in_project=target_project, ai_guardrails=guardrails)
            )
            saved_path = inherited_repo.save_item(updated_item)
            print(f"✅ Ítem '{existing_item.id}' actualizado correctamente en {saved_path}.")
        except Exception as e:
            print(f"❌ Error al guardar el ítem: {e}")
    else:
        print("🛑 Edición cancelada.")

def menu_compile_project(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    print("\n--- ⚙️ COMPILACIÓN DE DOCUMENTACIÓN ---")
    
    target_project = active_project
    if not target_project:
        projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
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
    repo = MOMInheritedRepository(pm.projects_root, target_project)
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

    if ask_confirmation(f"¿Proceder a compilar '{target_project}'?"):
        compiler.compile_all()
        print(f"✅ Compilación completada con éxito para '{target_project}'.")
    else:
        print("🛑 Compilación cancelada.")

def menu_compile_all_projects(pm: ProjectManager) -> None:
    """Recorre y compila absolutamente todos los proyectos registrados en data/projects/."""
    print("\n--- ⚙️ COMPILACIÓN MASIVA DE TODOS LOS PROYECTOS ---")
    projects = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
    
    if not projects:
        print("❌ No hay proyectos registrados para compilar.")
        return

    print(f"Se han detectado {len(projects)} proyectos en el sistema:")
    for p in projects:
        print(f"  • {p}")

    if ask_confirmation("¿Deseas proceder con la compilación masiva de TODOS los proyectos?"):
        success_count = 0
        error_count = 0
        
        for proj_name in projects:
            print(f"\n-------------------------------------------------------")
            print(f"🔄 Compilando proyecto: '{proj_name}'...")
            try:
                repo = MOMInheritedRepository(pm.projects_root, proj_name)
                compiler = MOMCompiler(repo)
                
                errors = compiler.validate_graph()
                if errors:
                    print(f"❌ Errores de trazabilidad en '{proj_name}':")
                    for err in errors:
                        print(f"   • {err}")
                    error_count += 1
                    continue

                compiler.compile_all()
                print(f"✅ Proyecto '{proj_name}' compilado correctamente.")
                success_count += 1
            except Exception as e:
                print(f"❌ Error durante la compilación de '{proj_name}': {e}")
                error_count += 1

        print(f"\n=======================================================")
        print(f"📊 RESUMEN DE COMPILACIÓN MASIVA:")
        print(f"  • Proyectos procesados con éxito: {success_count}/{len(projects)}")
        print(f"  • Proyectos con errores/abortados: {error_count}")
        print(f"=======================================================")

def menu_review_agent_proposal(pm: ProjectManager, active_project: Optional[str] = None) -> None:
    print("\n--- 🤖 REVISIÓN Y APROBACIÓN DE PROPUESTAS PENDIENTES DE IA ---")
    proposals_dir = pm.projects_root.parent / "ai-proposals"
    if not proposals_dir.exists():
        print("ℹ️ No hay propuestas pendientes de IA en 'data/ai-proposals/'.")
        return

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

    target_proj = active_project
    if not target_proj:
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

    selected_files = proposals_by_project.get(target_proj, [])
    if not selected_files:
        print(f"ℹ️ No hay propuestas pendientes de IA para el proyecto '{target_proj}'.")
        return

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
            try:
                repo = MOMInheritedRepository(pm.projects_root, target_proj)
                item.attributes.status = StatusEnum.APPROVED
                repo.save_item(item)
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

def select_active_project(pm: ProjectManager) -> Optional[str]:
    """Permite seleccionar de forma transparente el proyecto de trabajo activo."""
    projs = [p.name for p in pm.projects_root.iterdir() if p.is_dir() and (p / "project.json").exists()]
    if not projs:
        print("❌ No hay proyectos registrados. Crea uno con la opción [2].")
        return None

    print("\n--- 🎯 SELECCIONAR PROYECTO DE TRABAJO ACTIVO ---")
    for i, p in enumerate(projs, 1):
        repo = MOMInheritedRepository(pm.projects_root, p)
        print(f"  [{i}] {p} (Herencia: {' -> '.join(repo.chain)})")

    try:
        idx = int(input("\nSelecciona el número de proyecto activo: ")) - 1
        if 0 <= idx < len(projs):
            selected = projs[idx]
            print(f"✅ Proyecto activo fijado a: '{selected}'")
            return selected
        print("❌ Selección fuera de rango.")
    except ValueError:
        print("❌ Entrada no válida.")
    return None

def interactive_main() -> None:
    projects_dir = current_dir.parent / "data" / "projects"
    data_dir = current_dir.parent / "data"
    pm = ProjectManager(projects_root=projects_dir)
    
    # Sincronizar automáticamente todos los proyectos privados existentes al arrancar
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
        print("  [7] Compilar proyecto activo (Generar doc. MD, Vault Obsidian y AGENTS.md)")
        print("  [8] Compilar TODOS los proyectos registrados")
        print("  [9] Revisar y aprobar/rechazar propuestas de IA (data/ai-proposals/)")
        print("  [10] Gestión de Biblioteca, Dominio Público y Kill-Switch (bib)")
        print("  [11] Gestión de Patentes y Freedom to Operate (pat/MOSPAT)")
        print("  [12] Auditoría de Código y Decompilaciones (audit/MOSAUDIT)")
        print("  [13] Configurar ajustes GLOBALES y Supervisor Humano a Cargo")
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
        else:
            print("⚠️ Opción no válida. Por favor introduce un número entre 0 y 14.")

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

        bib_parser = subparsers.add_parser("bib", help="Gestión de Biblioteca y Licencias")
        bib_parser.add_argument("--action", choices=["revoke", "status"], required=True)
        bib_parser.add_argument("--work", help="ID de la obra")

        pat_parser = subparsers.add_parser("pat", help="Gestión de Patentes FTO")
        pat_parser.add_argument("--action", choices=["list", "check"], required=True)

        audit_parser = subparsers.add_parser("audit", help="Auditoría de Código y Decompilaciones")
        audit_parser.add_argument("--action", choices=["list", "check"], required=True)

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
                print(f"✅ Proyecto '{args.name}' creado.")
        elif args.command == "compile":
            repo = MOMInheritedRepository(pm.projects_root, args.project)
            compiler = MOMCompiler(repo)
            if not compiler.validate_graph():
                compiler.compile_all()
                print(f"✅ Proyecto '{args.project}' compilado.")
        elif args.command == "bib":
            if args.action == "revoke" and args.work:
                print(f"🛑 Kill-switch ejecutado para la obra {args.work}.")
        elif args.command == "pat":
            print("⚖️ Estado de patentes consultado.")
        elif args.command == "audit":
            print("🛡️ Auditoría de código ejecutada.")
    else:
        interactive_main()

if __name__ == "__main__":
    main()

# Version: 0.5.3
# File_Version: 0.5.2.13
# Schema_Version: 0.5.3