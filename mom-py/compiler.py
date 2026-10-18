import shutil
import json
import re
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from projects import MOMInheritedRepository
from schemas import ESAPhase, MOMItem, MetsuOSKnowledgeLevel, CURRENT_SCHEMA_VERSION

class MOMCompiler:
    """Compilador de especificaciones atómicas, generador de entregables, Obsidian Vault local, Vault Global e Integración Web."""
    def __init__(self, repo: MOMInheritedRepository, target_docs_dir: Optional[Path] = None) -> None:
        self.repo = repo
        self.project_dir = repo.project_dir
        self.doc_out = self.project_dir / "doc"
        self.vault_out = self.project_dir / "vault"
        self.agents_out = self.project_dir / "AGENTS.md"
        self.target_docs_dir = target_docs_dir or repo.target_docs_dir
        
        # Directorio de datos raíz y Vault global unificado en data/vault/
        self.data_dir = self.project_dir.parent.parent
        self.global_vault_dir = self.data_dir / "vault"
        self.projects_dir = self.data_dir / "projects"
        
        self.local_templates_dir = self.project_dir / "templates"
        self.global_templates_dir = self.data_dir / "templates"

        # Cargar configuración global desde data/config.json
        self.global_config = self._load_global_config()

    def _load_global_config(self) -> dict:
        """Carga la configuración global desde data/config.json."""
        config_file = self.data_dir / "config.json"
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Error al leer data/config.json: {e}")
        return {"web_vault_dir": None, "schema_version": CURRENT_SCHEMA_VERSION}

    def _get_template_content(self, template_name: str) -> Optional[str]:
        """Obtiene el contenido de una plantilla, priorizando la carpeta local sobre la global."""
        local_file = self.local_templates_dir / template_name
        if local_file.exists():
            with open(local_file, "r", encoding="utf-8") as f:
                return f.read()
        
        global_file = self.global_templates_dir / template_name
        if global_file.exists():
            with open(global_file, "r", encoding="utf-8") as f:
                return f.read()
                
        return None

    def _resolve_bidirectional_relationships(self, all_items: Dict[str, MOMItem]) -> None:
        """Calcula explícitamente los child_ids de cada elemento a partir de los parent_ids declarados."""
        for item in all_items.values():
            item.child_ids = []

        for item_id, item in all_items.items():
            for parent_id in item.parent_ids:
                if parent_id in all_items:
                    parent_item = all_items[parent_id]
                    if item_id not in parent_item.child_ids:
                        parent_item.child_ids.append(item_id)

    def validate_graph(self) -> List[str]:
        """Valida la integridad del grafo ESA/MOM acumulado por herencia."""
        errors: List[str] = []
        all_items = self.repo.list_all_consolidated()

        for item_id, item in all_items.items():
            for pid in item.parent_ids:
                if pid not in all_items:
                    errors.append(f"[{item.id}] (de '{item.metadata.declared_in_project}') apunta a parent_id inexistente: '{pid}'")

            phase_val = item.phase.value.lower() if hasattr(item.phase, 'value') else str(item.phase).lower()
            if phase_val not in ("cor", "urd") and not item.parent_ids:
                errors.append(f"[{item.id}] El elemento de fase '{phase_val.upper()}' no tiene padres.")

        return errors

    def _build_item_mermaid_local(self, item: MOMItem) -> str:
        """Genera un diagrama Mermaid local centrado en el elemento, mostrando sus padres e hijos inmediatos."""
        lines = ["```mermaid", "graph TD"]
        lines.append(f"    {item.id}[{item.id}]")

        for pid in item.parent_ids:
            lines.append(f"    {pid}[{pid}] --> {item.id}")

        for cid in item.child_ids:
            lines.append(f"    {item.id} --> {cid}[{cid}]")

        lines.append("```")
        return "\n".join(lines)

    def _build_phase_mermaid_graph(self, phase_items: List[MOMItem], all_items: Dict[str, MOMItem]) -> str:
        """Genera el grafo Mermaid completo para todos los elementos de una fase ESA."""
        if not phase_items:
            return "*(No hay elementos para representar en el grafo)*"

        phase_item_ids = {item.id for item in phase_items}
        lines = ["```mermaid", "graph TD"]

        for item in phase_items:
            lines.append(f"    {item.id}[{item.id}]")

        for item in phase_items:
            for pid in item.parent_ids:
                if pid in phase_item_ids:
                    lines.append(f"    {pid} --> {item.id}")
                else:
                    lines.append(f"    {pid}[{pid}] -.-> {item.id}")

        lines.append("```")
        return "\n".join(lines)

    def _build_item_markdown_block(self, item: MOMItem) -> str:
        """Construye un bloque Markdown detallado para un MOMItem."""
        attr = item.attributes
        meta = item.metadata

        guardrail = f"\n> 🛑 **AI Guardrails (Inmutable):** {meta.ai_guardrails}\n" if meta.ai_guardrails else ""
        parents = f"**Padres:** {', '.join([f'[[{pid}]]' for pid in item.parent_ids])}\n" if item.parent_ids else ""
        children = f"**Hijos:** {', '.join([f'[[{cid}]]' for cid in item.child_ids])}\n" if item.child_ids else ""
        origin_proj = meta.declared_in_project or self.repo.project_name
        origin = f"**Origen:** `{origin_proj}`\n"

        kl_str = ""
        if attr.metsuos_knowledge_level:
            kl_val = attr.metsuos_knowledge_level.value if hasattr(attr.metsuos_knowledge_level, 'value') else str(attr.metsuos_knowledge_level)
            kl_str = f" | **Nivel MetsuOS:** `{kl_val}`"

        nato_str = ""
        if attr.nato_source_reliability or attr.nato_information_credibility:
            rel = attr.nato_source_reliability or "?"
            cred = attr.nato_information_credibility or "?"
            nato_str = f" | **Evaluación OTAN:** `{rel}{cred}`"

        bib_lines: List[str] = []
        if attr.bib_title or attr.bib_source:
            authors = f" - {', '.join(attr.bib_authors)}" if attr.bib_authors else ""
            title = f"*{attr.bib_title}*" if attr.bib_title else "Fuente sin título"
            source = f" [{attr.bib_source}]" if attr.bib_source else ""
            detail = f" (Cita/Detalle: {attr.bib_citation_detail})" if attr.bib_citation_detail else ""
            bib_lines.append(f"**Referencia Bibliográfica:** {title}{authors}{source}{detail}")

        bib_block = "\n".join(bib_lines) + "\n\n" if bib_lines else ""

        status_val = attr.status.value if hasattr(attr.status, 'value') else str(attr.status)
        prio_val = attr.priority.value if hasattr(attr.priority, 'value') else str(attr.priority)
        verif_val = attr.verification_method.value if hasattr(attr.verification_method, 'value') else str(attr.verification_method)

        block = f"### {item.id}: {item.title}\n" \
                f"**Estado:** `{status_val}` | **Prioridad:** `{prio_val}` | **Verificación:** `{verif_val}`{kl_str}{nato_str} | {origin}\n\n" \
                f"#### Descripción\n{item.description}\n\n" \
                f"{bib_block}" \
                f"{parents}{children}{guardrail}\n---"
        return block

    def compile_obsidian_vault(self) -> None:
        """Genera notas Markdown individuales en vault/, INDEX.md y sincroniza con data/vault/."""
        if self.vault_out.exists():
            shutil.rmtree(self.vault_out)
        self.vault_out.mkdir(parents=True, exist_ok=True)

        all_items = self.repo.list_all_consolidated()
        
        self._resolve_bidirectional_relationships(all_items)

        for item in all_items.values():
            phase_val = item.phase.value.lower() if hasattr(item.phase, 'value') else str(item.phase).lower()
            phase_dir = self.vault_out / phase_val.upper()
            phase_dir.mkdir(parents=True, exist_ok=True)

            attr = item.attributes
            meta = item.metadata

            parents_links = ", ".join([f"[[{pid}]]" for pid in item.parent_ids]) if item.parent_ids else "Ninguno (Raíz)"
            children_links = ", ".join([f"[[{cid}]]" for cid in item.child_ids]) if item.child_ids else "Ninguno"
            guardrail = f"\n> 🛑 **AI Guardrails (Inmutable):** {meta.ai_guardrails}" if meta.ai_guardrails else ""

            kl_val = attr.metsuos_knowledge_level.value if hasattr(attr.metsuos_knowledge_level, 'value') else str(attr.metsuos_knowledge_level) if attr.metsuos_knowledge_level else ""
            kl_field = f'metsuos_knowledge_level: "{kl_val}"\n' if kl_val else ""
            nato_field = f'nato_eval: "{attr.nato_source_reliability or "?"}{attr.nato_information_credibility or "?"}"\n' if (attr.nato_source_reliability or attr.nato_information_credibility) else ""

            bib_info = ""
            if attr.bib_title or attr.bib_source:
                authors = f" de {', '.join(attr.bib_authors)}" if attr.bib_authors else ""
                detail = f" - Detalle: {attr.bib_citation_detail}" if attr.bib_citation_detail else ""
                bib_info = f"\n## Referencia Bibliográfica\n* **Fuente:** {attr.bib_title or 'Sin título'}{authors} (`{attr.bib_source or 'N/A'}`){detail}\n"

            status_val = attr.status.value if hasattr(attr.status, 'value') else str(attr.status)
            prio_val = attr.priority.value if hasattr(attr.priority, 'value') else str(attr.priority)
            declared_project = meta.declared_in_project or self.repo.project_name

            item_mermaid = self._build_item_mermaid_local(item)

            file_content = f"""---
id: "{item.id}"
phase: "{phase_val}"
title: "{item.title}"
status: "{status_val}"
priority: "{prio_val}"
author: "{meta.author}"
declared_in: "{declared_project}"
schema_version: "{item.schema_version}"
{kl_field}{nato_field}---

# {item.id}: {item.title}

## Descripción
{item.description}
{bib_info}
## Trazabilidad y Relaciones

{item_mermaid}

* **Proyecto Origen:** `{declared_project}`
* **Padres:** {parents_links}
* **Hijos:** {children_links}
{guardrail}
"""
            note_file = phase_dir / f"{item.id}.md"
            with open(note_file, "w", encoding="utf-8") as f:
                f.write(file_content)

        index_template = self._get_template_content("INDEX.md.template") or "# INDEX\n\nProyecto: {{PROJECT_NAME}}\n"
        chain_str = " -> ".join(self.repo.chain)
        index_content = index_template.replace("{{PROJECT_NAME}}", self.repo.project_name).replace("{{INHERITANCE_CHAIN}}", chain_str)
        with open(self.vault_out / "INDEX.md", "w", encoding="utf-8") as f:
            f.write(index_content)

        for phase in ESAPhase:
            doc_file = self.doc_out / f"{phase.value.upper()}.md"
            if doc_file.exists():
                shutil.copy(doc_file, self.vault_out / f"{phase.value.upper()}.md")
        
        vision_file = self.doc_out / "VISION.md"
        if vision_file.exists():
            shutil.copy(vision_file, self.vault_out / "VISION.md")

        if self.agents_out.exists():
            shutil.copy(self.agents_out, self.vault_out / "AGENTS.md")

        self._sync_to_global_vault()

    def _sync_to_global_vault(self) -> None:
        """Sincroniza el Vault del proyecto actual en data/vault/<PROJECT_ID>/ y regenera el INDEX.md Global."""
        self.global_vault_dir.mkdir(parents=True, exist_ok=True)
        
        target_proj_vault = self.global_vault_dir / self.repo.project_name
        if target_proj_vault.exists():
            shutil.rmtree(target_proj_vault)
        
        shutil.copytree(self.vault_out, target_proj_vault)
        self._generate_global_vault_index()

        # Exportar el Vault Global completo a la carpeta plana web si está configurada
        self._export_to_flat_web_vault()

    def _generate_global_vault_index(self) -> None:
        """Genera el INDEX.md raíz de data/vault/ con grafo Mermaid y leyenda ordenada alfabéticamente."""
        public_projects: Dict[str, dict] = {}

        if self.projects_dir.exists():
            for p in self.projects_dir.iterdir():
                p_json = p / "project.json"
                if p.is_dir() and p_json.exists():
                    try:
                        with open(p_json, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        if not meta.get("is_private", False):
                            public_projects[p.name] = {
                                "id": meta.get("project_id", p.name),
                                "name": meta.get("name", p.name),
                                "phase": meta.get("phase", "COR"),
                                "parents": meta.get("parents", []),
                                "description": meta.get("description", "Sin descripción")
                            }
                    except Exception:
                        pass

        mermaid_lines: List[str] = ["graph TD"]
        for pid in sorted(public_projects.keys()):
            mermaid_lines.append(f"    {pid}[{pid}]")

        for pid, data in sorted(public_projects.items()):
            for parent_id in data["parents"]:
                if parent_id in public_projects:
                    mermaid_lines.append(f"    {parent_id} --> {pid}")

        mermaid_str = "\n".join(mermaid_lines)

        legend_lines: List[str] = []
        for pid in sorted(public_projects.keys()):
            data = public_projects[pid]
            desc_str = f" - {data['description']}" if data['description'] else ""
            legend_lines.append(f"1. **[[{pid}/INDEX|{pid}]]**: {data['name']} (`Fase {data['phase']}`){desc_str}")

        legend_str = "\n".join(legend_lines) if legend_lines else "*(No hay proyectos públicos registrados)*"

        global_index_content = f"""# 🌐 METSUOS METHODOLOGY (MOM) - VAULT GLOBAL DE CONOCIMIENTO

> **Visión Holística del Sistema:** Este Vault consolida todos los proyectos públicos de MetsuOS y resuelve el grafo DAG de herencia de conocimiento y especificaciones atómicas.

---

## 🌳 Grafo de Jerarquía de Proyectos

```mermaid
{mermaid_str}
```

---

## 📋 Leyenda y Accesos Directos a Proyectos

{legend_str}

---
*Última compilación global realizada por el proyecto: `{self.repo.project_name}`*
"""

        with open(self.global_vault_dir / "INDEX.md", "w", encoding="utf-8") as f:
            f.write(global_index_content)

    def _export_to_flat_web_vault(self) -> None:
        """Exporta TODO el Vault Global a la carpeta web con formato [[enlace_real|etiqueta_local]]."""
        raw_web_dir = self.global_config.get("web_vault_dir")
        if not raw_web_dir:
            return

        web_path = Path(raw_web_dir).expanduser().resolve()
        if not web_path.exists():
            print(f"ℹ️  [WEB VAULT] La ruta configurada '{web_path}' no existe en el disco. Omitiendo exportación web.")
            return

        print(f"\n🌐 [WEB VAULT] Sincronizando Vault Global plano en: {web_path}")

        # 1. Limpiar EXCLUSIVAMENTE los archivos que empiezan por 'MOM-'
        for existing_file in web_path.glob("MOM-*.md"):
            try:
                existing_file.unlink()
            except Exception as e:
                print(f"⚠️ Error al limpiar archivo web previo '{existing_file.name}': {e}")

        now_str = datetime.datetime.now().strftime("%Y-%m-%d")
        phase_names = {"COR", "URD", "SRD", "ADD", "DDD", "VISION", "AGENTS", "INDEX"}

        def rewrite_wikilinks(content: str, current_proj_context: str) -> str:
            """Mapea wikilinks a [[MOM-PROYECTO-RECURSO|ETIQUETA_LOCAL]]."""
            def replace_link(match):
                raw_inner = match.group(1)
                
                if "|" in raw_inner:
                    target_part, visual_label = raw_inner.split("|", 1)
                else:
                    target_part = raw_inner
                    visual_label = raw_inner

                # Manejar rutas con barra ej. [[MOSCON/INDEX]]
                if "/" in target_part:
                    parts = [p for p in target_part.split("/") if p]
                    if len(parts) >= 2 and parts[1] == "INDEX":
                        target_part = f"{parts[0]}-INDEX"
                    elif len(parts) >= 2 and parts[1] in phase_names:
                        target_part = f"{parts[0]}-{parts[1]}"
                    else:
                        target_part = parts[-1]

                segments = target_part.split("-")

                # Calcular el destino real
                if len(segments) >= 3 and segments[0] == "MOM" and segments[1] == current_proj_context:
                    real_target = target_part
                elif len(segments) >= 2 and segments[0] == "MOM":
                    if segments[1] != current_proj_context:
                        real_target = f"MOM-{current_proj_context}-" + "-".join(segments[1:])
                    else:
                        real_target = target_part
                elif target_part.upper() in phase_names:
                    real_target = f"MOM-{current_proj_context}-{target_part.upper()}"
                else:
                    real_target = f"MOM-{current_proj_context}-{target_part}"

                return f"[[{real_target}|{visual_label}]]"

            return re.sub(r'\[\[(.*?)\]\]', replace_link, content)

        updated_count = 0

        # 2. Recorrer TODOS los proyectos registrados en data/projects/
        if self.projects_dir.exists():
            for proj_folder in self.projects_dir.iterdir():
                if not proj_folder.is_dir() or not (proj_folder / "project.json").exists():
                    continue

                proj_name = proj_folder.name
                proj_repo = MOMInheritedRepository(self.projects_dir, proj_name)
                all_items = proj_repo.list_all_consolidated()
                self._resolve_bidirectional_relationships(all_items)

                # Exportar notas atómicas de este proyecto
                for item in all_items.values():
                    phase_val = item.phase.value.lower() if hasattr(item.phase, 'value') else str(item.phase).lower()
                    attr = item.attributes
                    meta = item.metadata

                    web_file_name = f"MOM-{proj_name}-{item.id}.md"
                    web_item_id = f"MOM-{proj_name}-{item.id}"

                    # Generar enlaces a PADRES resolviendo el proyecto origen real
                    parents_list = []
                    parent_yaml_lines = []
                    for pid in item.parent_ids:
                        p_owner = all_items[pid].metadata.declared_in_project if (pid in all_items and all_items[pid].metadata and all_items[pid].metadata.declared_in_project) else proj_name
                        real_p_id = f"MOM-{p_owner}-{pid}"
                        parents_list.append(f"[[{real_p_id}|{pid}]]")
                        parent_yaml_lines.append(f'  - "{real_p_id}"')

                    parents_links = ", ".join(parents_list) if parents_list else "Ninguno (Raíz)"
                    parent_yaml_block = "\n".join(parent_yaml_lines) if parent_yaml_lines else "  []"

                    # Generar enlaces a HIJOS resolviendo el proyecto origen real
                    children_list = []
                    child_yaml_lines = []
                    for cid in item.child_ids:
                        c_owner = all_items[cid].metadata.declared_in_project if (cid in all_items and all_items[cid].metadata and all_items[cid].metadata.declared_in_project) else proj_name
                        real_c_id = f"MOM-{c_owner}-{cid}"
                        children_list.append(f"[[{real_c_id}|{cid}]]")
                        child_yaml_lines.append(f'  - "{real_c_id}"')

                    children_links = ", ".join(children_list) if children_list else "Ninguno"
                    child_yaml_block = "\n".join(child_yaml_lines) if child_yaml_lines else "  []"

                    guardrail = f"\n> 🛑 **AI Guardrails (Inmutable):** {meta.ai_guardrails}" if meta.ai_guardrails else ""

                    kl_val = attr.metsuos_knowledge_level.value if hasattr(attr.metsuos_knowledge_level, 'value') else str(attr.metsuos_knowledge_level) if attr.metsuos_knowledge_level else ""
                    nato_eval = f"{attr.nato_source_reliability or '?'}{attr.nato_information_credibility or '?'}" if (attr.nato_source_reliability or attr.nato_information_credibility) else ""

                    status_val = attr.status.value if hasattr(attr.status, 'value') else str(attr.status)
                    prio_val = attr.priority.value if hasattr(attr.priority, 'value') else str(attr.priority)
                    declared_project = meta.declared_in_project or proj_name

                    item_mermaid = self._build_item_mermaid_local(item)

                    frontmatter = f"""---
id: "{web_item_id}"
title: "{item.title}"
iaStatus: 8
IAModel: "MOM 0.5.2.20 MetsuOS Methodology Framework"
date: "{now_str}"
lastmod: "{now_str}"
type: "atomic-spec"
phase: "{phase_val}"
status: "{status_val}"
priority: "{prio_val}"
author: "{meta.author}"
declared_in: "{declared_project}"
schema_version: "{item.schema_version}"
metsuos_knowledge_level: "{kl_val}"
nato_eval: "{nato_eval}"
tags:
  - "mom"
  - "{declared_project.lower()}"
  - "{phase_val}"
  - "metsuos"
parent_ids:
{parent_yaml_block}
child_ids:
{child_yaml_block}
---

# {item.id}: {item.title}

## Descripción
{item.description}

## Trazabilidad y Relaciones

{item_mermaid}

* **Proyecto Origen:** `{declared_project}`
* **Padres:** {parents_links}
* **Hijos:** {children_links}
{guardrail}
"""
                    dest_file = web_path / web_file_name
                    with open(dest_file, "w", encoding="utf-8") as f:
                        f.write(frontmatter)
                    updated_count += 1

                # Exportar documentos de Fase, VISION, AGENTS e INDEX de cada proyecto
                proj_doc_dir = proj_folder / "doc"
                proj_vault_dir = proj_folder / "vault"

                for phase in ESAPhase:
                    doc_file = proj_doc_dir / f"{phase.value.upper()}.md"
                    if doc_file.exists():
                        with open(doc_file, "r", encoding="utf-8") as f:
                            raw_content = f.read()

                        content = rewrite_wikilinks(raw_content, current_proj_context=proj_name)
                        frontmatter = f"""---
id: "MOM-{proj_name}-{phase.value.upper()}"
title: "Documento {phase.value.upper()} - {proj_name}"
iaStatus: 8
IAModel: "MOM 0.5.2.20 MetsuOS Methodology Framework"
date: "{now_str}"
lastmod: "{now_str}"
type: "phase-doc"
phase: "{phase.value.lower()}"
declared_in: "{proj_name}"
---

{content}
"""
                        dest_file = web_path / f"MOM-{proj_name}-{phase.value.upper()}.md"
                        with open(dest_file, "w", encoding="utf-8") as f:
                            f.write(frontmatter)
                        updated_count += 1

                for doc_name, doc_type in [("VISION", "vision-doc"), ("AGENTS", "agents-context"), ("INDEX", "project-index")]:
                    src_file = proj_doc_dir / f"{doc_name}.md" if doc_name != "INDEX" else proj_vault_dir / "INDEX.md"
                    if src_file.exists():
                        with open(src_file, "r", encoding="utf-8") as f:
                            raw_content = f.read()

                        content = rewrite_wikilinks(raw_content, current_proj_context=proj_name)
                        frontmatter = f"""---
id: "MOM-{proj_name}-{doc_name}"
title: "{doc_name} - {proj_name}"
iaStatus: 8
IAModel: "MOM 0.5.2.20 MetsuOS Methodology Framework"
date: "{now_str}"
lastmod: "{now_str}"
type: "{doc_type}"
declared_in: "{proj_name}"
---

{content}
"""
                        dest_file = web_path / f"MOM-{proj_name}-{doc_name}.md"
                        with open(dest_file, "w", encoding="utf-8") as f:
                            f.write(frontmatter)
                        updated_count += 1

        # 3. Exportar el INDEX Global Raíz del Vault de MOM
        global_index_src = self.global_vault_dir / "INDEX.md"
        if global_index_src.exists():
            with open(global_index_src, "r", encoding="utf-8") as f:
                raw_content = f.read()

            content = rewrite_wikilinks(raw_content, current_proj_context="MOM")

            global_frontmatter = f"""---
id: "MOM-INDEX"
title: "MetsuOS Methodology (MOM) - Vault Global de Conocimiento"
iaStatus: 8
IAModel: "MOM 0.5.2.20 MetsuOS Methodology Framework"
date: "{now_str}"
lastmod: "{now_str}"
type: "project-index"
declared_in: "MOM"
---

{content}
"""
            with open(web_path / "MOM-INDEX.md", "w", encoding="utf-8") as f:
                f.write(global_frontmatter)
            updated_count += 1

        print(f"✅ [WEB VAULT] Sincronización completa del Vault Global finalizada ({updated_count} archivos exportados).")
        print("--------------------------------------------------------------------------------")
        print(f"📌 Punto de Entrada Web (Índice Global MOM): MOM-INDEX.md")
        print(f"   Ruta relativa de enlace en tu web: [[MOM-INDEX]]")
        print("--------------------------------------------------------------------------------\n")

    def compile_all(self) -> None:
        """Genera todos los entregables usando plantillas de contexto + volcado atómico."""
        self.doc_out.mkdir(parents=True, exist_ok=True)
        self.vault_out.mkdir(parents=True, exist_ok=True)
        all_items = self.repo.list_all_consolidated()
        
        self._resolve_bidirectional_relationships(all_items)

        # 1. Compilar VISION.md
        philosophy_file = self.project_dir / "VISION_PHILOSOPHY.md"
        if philosophy_file.exists():
            with open(philosophy_file, "r", encoding="utf-8") as f:
                philosophy_text = f.read().strip()
            if not philosophy_text:
                philosophy_text = "> ⚠️ **[PENDIENTE DE DEFINICIÓN]**\n\n*(El archivo VISION_PHILOSOPHY.md existe pero está vacío. Edita este archivo en el directorio del proyecto para incluir el marco doctrinal de este dominio)*"
                print(f"⚠️  [ADVERTENCIA] El archivo '{philosophy_file.name}' del proyecto '{self.repo.project_name}' está VACÍO.")
        else:
            philosophy_file.touch()
            philosophy_text = "> ⚠️ **[PENDIENTE DE DEFINICIÓN]**\n\n*(No se ha definido un archivo VISION_PHILOSOPHY.md para este proyecto. Se ha creado el archivo vacío en el disco para su edición)*"
            print(f"\n=======================================================")
            print(f"⚠️  [ADVERTENCIA] Falta la filosofía del proyecto '{self.repo.project_name}'")
            print(f"   Se ha creado el archivo vacío en: {philosophy_file}")
            print(f"   Por favor, edita ese archivo para definir la visión del dominio.")
            print(f"=======================================================\n")

        vision_template = self._get_template_content("VISION.md.template") or "# VISION\n\n{{PROJECT_PHILOSOPHY}}\n"
        proj_display_name = self.repo.config.name or self.repo.project_name
        vision_rendered = (
            vision_template
            .replace("{{PROJECT_NAME}}", proj_display_name)
            .replace("{{PROJECT_ID}}", self.repo.project_name)
            .replace("{{PROJECT_PHILOSOPHY}}", philosophy_text)
        )
        with open(self.doc_out / "VISION.md", "w", encoding="utf-8") as f:
            f.write(vision_rendered)

        # 2. Compilar documentos por fase ESA
        for phase in ESAPhase:
            phase_items = [
                i for i in all_items.values() 
                if (isinstance(i.phase, str) and i.phase.lower() == phase.value.lower()) or 
                (hasattr(i.phase, 'value') and i.phase.value.lower() == phase.value.lower())
            ]
            phase_items.sort(key=lambda x: x.id)

            phase_graph = self._build_phase_mermaid_graph(phase_items, all_items)
            blocks = [self._build_item_markdown_block(item) for item in phase_items]
            items_rendered = "\n\n".join(blocks) if blocks else "*(No hay especificaciones atómicas registradas en esta fase)*"
            
            template_str = self._get_template_content(f"{phase.value.upper()}.md.template") or f"# Documento ESA - Fase {phase.value.upper()}\n\n## Grafo de Trazabilidad de la Fase\n\n{{MOM_PHASE_GRAPH}}\n\n## Especificaciones Atómicas\n\n{{MOM_ATOMIC_ITEMS}}\n"
            
            if "{{MOM_PHASE_GRAPH}}" not in template_str:
                template_str = template_str.replace(
                    "{{MOM_ATOMIC_ITEMS}}", 
                    "## 📊 Grafo de Trazabilidad de la Fase\n\n{{MOM_PHASE_GRAPH}}\n\n---\n\n{{MOM_ATOMIC_ITEMS}}"
                )

            doc_content = (
                template_str
                .replace("{{PROJECT_NAME}}", proj_display_name)
                .replace("{{MOM_PHASE_GRAPH}}", phase_graph)
                .replace("{{MOM_ATOMIC_ITEMS}}", items_rendered)
            )

            with open(self.doc_out / f"{phase.value.upper()}.md", "w", encoding="utf-8") as f:
                f.write(doc_content)

        # 3. Compilar AGENTS.md
        guardrail_items = [i for i in all_items.values() if i.metadata and i.metadata.ai_guardrails]
        blocks = [f"### Componente `{i.id}` ({i.title}) - Origen: `{i.metadata.declared_in_project or self.repo.project_name}`\n> 🛑 **Guardrail Inmutable:** {i.metadata.ai_guardrails}\n" for i in guardrail_items]
        agents_content = f"# AGENTS.md - Contexto de Onboarding e Instrucciones para IA\n**Proyecto:** {proj_display_name} | **Esquema:** v{CURRENT_SCHEMA_VERSION}\n\n"
        agents_content += "\n".join(blocks) if blocks else "*(No se han definido guardrails inmutables en las especificaciones actuales)*"
        
        with open(self.agents_out, "w", encoding="utf-8") as f:
            f.write(agents_content)

        self.compile_obsidian_vault()

        if self.target_docs_dir:
            self.target_docs_dir.mkdir(parents=True, exist_ok=True)
            for md_file in self.doc_out.glob("*.md"):
                shutil.copy(md_file, self.target_docs_dir / md_file.name)
            if self.agents_out.exists():
                shutil.copy(self.agents_out, self.target_docs_dir / "AGENTS.md")

# Version: 0.5.2
# File_Version: 0.5.2.20
# Schema_Version: 0.5.2