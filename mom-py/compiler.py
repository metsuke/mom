import shutil
from pathlib import Path
from typing import Dict, List, Optional
from projects import MOMInheritedRepository
from schemas import ESAPhase, MOMItem

class MOMCompiler:
    """Compilador de especificaciones atómicas y generador de entregables con plantillas agnósticas (incluyendo COR y VISION) y Obsidian Vault."""
    def __init__(self, repo: MOMInheritedRepository, target_docs_dir: Optional[Path] = None) -> None:
        self.repo = repo
        self.project_dir = repo.project_dir
        self.doc_out = self.project_dir / "doc"
        self.vault_out = self.project_dir / "vault"
        self.agents_out = self.project_dir / "AGENTS.md"
        self.target_docs_dir = target_docs_dir or repo.target_docs_dir
        
        # Jerarquía de plantillas: 1. Proyecto local (data/projects/<proj>/templates) -> 2. Compartidas (data/templates)
        self.local_templates_dir = self.project_dir / "templates"
        self.global_templates_dir = self.project_dir.parent.parent / "templates"

    def _get_template_content(self, template_name: str) -> Optional[str]:
        """Obtiene el contenido de una plantilla, priorizando la carpeta local del proyecto sobre la global agnóstica."""
        local_file = self.local_templates_dir / template_name
        if local_file.exists():
            with open(local_file, "r", encoding="utf-8") as f:
                return f.read()
        
        global_file = self.global_templates_dir / template_name
        if global_file.exists():
            with open(global_file, "r", encoding="utf-8") as f:
                return f.read()
                
        return None

    def validate_graph(self) -> List[str]:
        """Valida la integridad del grafo ESA/MOM acumulado por herencia."""
        errors: List[str] = []
        all_items = self.repo.list_all_consolidated()

        for item_id, item in all_items.items():
            for pid in item.parent_ids:
                if pid not in all_items:
                    errors.append(f"[{item.id}] (de '{item.metadata.declared_in_project}') apunta a parent_id inexistente: '{pid}'")

            # COR y URD pueden no tener padres (son raíces del grafo). Fases posteriores (SRD, ADD, DDD) exigen herencia.
            if item.phase not in (ESAPhase.COR, ESAPhase.URD) and not item.parent_ids:
                errors.append(f"[{item.id}] El elemento de fase '{item.phase.value}' no tiene padres (debe heredar de URD, COR o fases previas).")

        return errors

    def compile_obsidian_vault(self) -> None:
        """Genera notas Markdown individuales en vault/, INDEX.md y copias completas navegables."""
        self.vault_out.mkdir(parents=True, exist_ok=True)
        all_items = self.repo.list_all_consolidated()

        # 1. Notas atómicas individuales por fase
        for item in all_items.values():
            phase_dir = self.vault_out / item.phase.value.upper()
            phase_dir.mkdir(parents=True, exist_ok=True)

            parents_links = ", ".join([f"[[{pid}]]" for pid in item.parent_ids]) if item.parent_ids else "Ninguno (Raíz)"
            children_links = ", ".join([f"[[{cid}]]" for cid in item.child_ids]) if item.child_ids else "Ninguno"
            guardrail = f"\n> 🛑 **AI Guardrails (Inmutable):** {item.metadata.ai_guardrails}" if item.metadata.ai_guardrails else ""

            file_content = f"""---
id: "{item.id}"
phase: "{item.phase.value}"
title: "{item.title}"
status: "{item.attributes.status.value}"
priority: "{item.attributes.priority.value}"
author: "{item.metadata.author}"
declared_in: "{item.metadata.declared_in_project}"
---

# {item.id}: {item.title}

## Descripción
{item.description}

## Trazabilidad y Relaciones
* **Origen:** `{item.metadata.declared_in_project}`
* **Padres:** {parents_links}
* **Hijos:** {children_links}
{guardrail}
"""
            note_file = phase_dir / f"{item.id}.md"
            with open(note_file, "w", encoding="utf-8") as f:
                f.write(file_content)

        # 2. Generación del INDEX.md del Vault basado en la plantilla agnóstica
        index_template = self._get_template_content("INDEX.md.template") or "# INDEX\n\nProyecto: {{PROJECT_NAME}}\n"
        chain_str = " -> ".join(self.repo.chain)
        index_content = index_template.replace("{{PROJECT_NAME}}", self.repo.project_name).replace("{{INHERITANCE_CHAIN}}", chain_str)
        with open(self.vault_out / "INDEX.md", "w", encoding="utf-8") as f:
            f.write(index_content)

        # 3. Copia de los documentos consolidados completos al Vault (incluyendo VISION si existe)
        for phase in ESAPhase:
            doc_file = self.doc_out / f"{phase.value.upper()}.md"
            if doc_file.exists():
                shutil.copy(doc_file, self.vault_out / f"{phase.value.upper()}.md")
        
        vision_file = self.doc_out / "VISION.md"
        if vision_file.exists():
            shutil.copy(vision_file, self.vault_out / "VISION.md")

    def compile_all(self) -> None:
        """Genera todos los entregables (VISION, COR, URD, SRD, ADD, DDD) usando plantillas de contexto + volcado atómico."""
        self.doc_out.mkdir(parents=True, exist_ok=True)
        self.vault_out.mkdir(parents=True, exist_ok=True)
        all_items = self.repo.list_all_consolidated()

        # 1. Compilación del Documento de Visión Narrativa (VISION.md) si existe la plantilla
        vision_template = self._get_template_content("VISION.md.template")
        if vision_template:
            vision_rendered = vision_template.replace("{{PROJECT_NAME}}", self.repo.project_name)
            with open(self.doc_out / "VISION.md", "w", encoding="utf-8") as f:
                f.write(vision_rendered)

        # 2. Compilación de documentos consolidados por fase ESA/MOM
        for phase in ESAPhase:
            phase_items = [i for i in all_items.values() if i.phase == phase]
            phase_items.sort(key=lambda x: x.id)

            blocks: List[str] = []
            for item in phase_items:
                guardrail = f"\n> ⚠️ **AI Guardrails:** {item.metadata.ai_guardrails}\n" if item.metadata.ai_guardrails else ""
                parents = f"**Padres:** {', '.join([f'[[{pid}]]' for pid in item.parent_ids])}\n" if item.parent_ids else ""
                children = f"**Hijos:** {', '.join([f'[[{cid}]]' for cid in item.child_ids])}\n" if item.child_ids else ""
                origin = f"**Origen:** `{item.metadata.declared_in_project}`\n"
                
                block = f"### {item.id}: {item.title}\n" \
                        f"**Estado:** `{item.attributes.status.value}` | **Prioridad:** `{item.attributes.priority.value}` | {origin}\n\n" \
                        f"#### Descripción\n{item.description}\n\n" \
                        f"{parents}{children}{guardrail}\n---"
                blocks.append(block)

            items_rendered = "\n\n".join(blocks) if blocks else "*(No hay especificaciones atómicas registradas en esta fase)*"
            
            # Cargar y renderizar plantilla de fase
            template_str = self._get_template_content(f"{phase.value.upper()}.md.template") or "# Documento ESA\n\n{{MOM_ATOMIC_ITEMS}}\n"
            doc_content = template_str.replace("{{PROJECT_NAME}}", self.repo.project_name).replace("{{MOM_ATOMIC_ITEMS}}", items_rendered)

            with open(self.doc_out / f"{phase.value.upper()}.md", "w", encoding="utf-8") as f:
                f.write(doc_content)

        # 3. Compilación del Vault para Obsidian
        self.compile_obsidian_vault()

        # 4. Compilación de AGENTS.md acumulado
        guardrail_items = [i for i in all_items.values() if i.metadata.ai_guardrails]
        blocks = [f"### Componente `{i.id}` ({i.title}) - Origen: `{i.metadata.declared_in_project}`\n> 🛑 **Guardrail Inmutable:** {i.metadata.ai_guardrails}\n" for i in guardrail_items]
        agents_content = "# AGENTS.md - Contexto de Onboarding e Instrucciones para IA\n\n" + "\n".join(blocks)
        with open(self.agents_out, "w", encoding="utf-8") as f:
            f.write(agents_content)

        # 5. Despliegue en la carpeta target configurada
        if self.target_docs_dir:
            self.target_docs_dir.mkdir(parents=True, exist_ok=True)
            for md_file in self.doc_out.glob("*.md"):
                shutil.copy(md_file, self.target_docs_dir / md_file.name)
            if self.agents_out.exists():
                shutil.copy(self.agents_out, self.target_docs_dir / "AGENTS.md")

# Version: 0.4.1